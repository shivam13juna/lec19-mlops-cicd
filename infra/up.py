"""Makes what the pipeline needs in AWS: the bucket, the role the endpoint runs as,
the two alarms that guard a release, and an IAM user for GitHub Actions with an
access key. It prints the key, once, for the two GitHub secrets.

    python infra/up.py

Safe to run twice. Each run makes a new access key and deletes the old one, so after
a second run the secrets in GitHub must be set again. Needs AWS credentials for us-west-2.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "release"))
from config import ACCOUNT, BUCKET, ENDPOINT, REGION, session  # noqa: E402

iam = session.client("iam")
s3 = session.client("s3")
cloudwatch = session.client("cloudwatch")

# The bucket the model files go into. Quick setup makes the same one.
try:
    s3.head_bucket(Bucket=BUCKET)
except s3.exceptions.ClientError:
    if REGION == "us-east-1":
        s3.create_bucket(Bucket=BUCKET)
    else:
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})


def role(role_name, trust, policy_name, policy):
    """Make the role if it is missing, and set its trust and its one inline policy either way."""
    try:
        iam.get_role(RoleName=role_name)
        iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=json.dumps(trust))
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust))
    iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy))


def allow(actions, resource="*", **condition):
    statement = {"Effect": "Allow", "Action": actions, "Resource": resource}
    if condition:
        statement["Condition"] = condition
    return statement


# The role the endpoint runs as: reads the model file, pulls AWS's container, writes logs,
# and reads the alarms during a release. DescribeAlarms has to be on "*". Narrowed to the
# alarms' own names, SageMaker cannot read them and rolls every release back.
role("hotel-release-exec",
     {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                                              "Principal": {"Service": "sagemaker.amazonaws.com"}}]},
     "run-endpoint",
     {"Version": "2012-10-17", "Statement": [
         allow("s3:GetObject", f"arn:aws:s3:::{BUCKET}/hotel/*"),
         allow(["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]),
         allow(["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]),
         allow("cloudwatch:DescribeAlarms")]})

# The two alarms a release is watched by. Any server error from the endpoint in a
# minute, or an average model time over half a second in two minutes running.
dimensions = [{"Name": "EndpointName", "Value": ENDPOINT}, {"Name": "VariantName", "Value": "AllTraffic"}]
cloudwatch.put_metric_alarm(
    AlarmName="hotel-release-errors", Namespace="AWS/SageMaker", MetricName="Invocation5XXErrors",
    Dimensions=dimensions, Statistic="Sum", Period=60, EvaluationPeriods=1, Threshold=1,
    ComparisonOperator="GreaterThanOrEqualToThreshold", TreatMissingData="notBreaching")
cloudwatch.put_metric_alarm(
    AlarmName="hotel-release-latency", Namespace="AWS/SageMaker", MetricName="ModelLatency",
    Dimensions=dimensions, Statistic="Average", Period=60, EvaluationPeriods=2, Threshold=500000,
    ComparisonOperator="GreaterThanThreshold", TreatMissingData="notBreaching")

# The user GitHub Actions signs in as. Unlike a role, a user has no trust policy, only a
# permission policy and a key. The register job, the deploy job and the rollback job all use it.
USER = "hotel-release-github"
try:
    iam.get_user(UserName=USER)
except iam.exceptions.NoSuchEntityException:
    iam.create_user(UserName=USER)
iam.put_user_policy(
    UserName=USER, PolicyName="release-model",
    PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
        allow(["s3:PutObject", "s3:GetObject"], f"arn:aws:s3:::{BUCKET}/hotel/releases/*"),
        allow(["sagemaker:DescribeModelPackageGroup", "sagemaker:CreateModelPackageGroup",
               "sagemaker:CreateModelPackage", "sagemaker:DescribeModelPackage",
               "sagemaker:UpdateModelPackage", "sagemaker:ListModelPackages"]),
        allow(["sagemaker:CreateModel", "sagemaker:DescribeModel", "sagemaker:CreateEndpointConfig",
               "sagemaker:DescribeEndpointConfig", "sagemaker:CreateEndpoint", "sagemaker:UpdateEndpoint",
               "sagemaker:DescribeEndpoint", "sagemaker:InvokeEndpoint"]),
        allow("iam:PassRole", f"arn:aws:iam::{ACCOUNT}:role/hotel-release-exec",
              StringEquals={"iam:PassedToService": "sagemaker.amazonaws.com"})]}))

# AWS shows a secret access key once, when the key is made, so a second run cannot print the
# old one. It deletes the old keys and makes a new one, which the secrets then have to match.
for old in iam.list_access_keys(UserName=USER)["AccessKeyMetadata"]:
    iam.delete_access_key(UserName=USER, AccessKeyId=old["AccessKeyId"])
key = iam.create_access_key(UserName=USER)["AccessKey"]
print(f"AWS_ACCESS_KEY_ID      {key['AccessKeyId']}")
print(f"AWS_SECRET_ACCESS_KEY  {key['SecretAccessKey']}")
