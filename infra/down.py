"""Deletes everything the pipeline and infra/up.py created in AWS.

    python infra/down.py

Safe to run twice. The bucket and its other contents are left alone.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "release"))
from config import ALARMS, BUCKET, ENDPOINT, GROUP, exists, session, sm  # noqa: E402

iam = session.client("iam")
s3 = session.client("s3")
cloudwatch = session.client("cloudwatch")

if exists(sm.describe_endpoint, EndpointName=ENDPOINT):
    sm.delete_endpoint(EndpointName=ENDPOINT)
    sm.get_waiter("endpoint_deleted").wait(EndpointName=ENDPOINT)
for c in sm.list_endpoint_configs(NameContains="hotel-release", MaxResults=100)["EndpointConfigs"]:
    sm.delete_endpoint_config(EndpointConfigName=c["EndpointConfigName"])
for m in sm.list_models(NameContains="hotel-release", MaxResults=100)["Models"]:
    sm.delete_model(ModelName=m["ModelName"])

if exists(sm.describe_model_package_group, ModelPackageGroupName=GROUP):
    for page in sm.get_paginator("list_model_packages").paginate(ModelPackageGroupName=GROUP):
        for p in page["ModelPackageSummaryList"]:
            sm.delete_model_package(ModelPackageName=p["ModelPackageArn"])
    # The group goes only once SageMaker has finished deleting its versions, so retry for a minute
    for _ in range(12):
        try:
            sm.delete_model_package_group(ModelPackageGroupName=GROUP)
            break
        except sm.exceptions.ClientError:
            time.sleep(5)
    else:
        sys.exit(f"the model group {GROUP} is still there, run this script again in a minute")

cloudwatch.delete_alarms(AlarmNames=ALARMS)
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="hotel/releases/"):
    for obj in page.get("Contents", []):
        s3.delete_object(Bucket=BUCKET, Key=obj["Key"])

try:
    for key in iam.list_access_keys(UserName="hotel-release-github")["AccessKeyMetadata"]:
        iam.delete_access_key(UserName="hotel-release-github", AccessKeyId=key["AccessKeyId"])
    for policy in iam.list_user_policies(UserName="hotel-release-github")["PolicyNames"]:
        iam.delete_user_policy(UserName="hotel-release-github", PolicyName=policy)
    iam.delete_user(UserName="hotel-release-github")
except iam.exceptions.NoSuchEntityException:
    pass
try:
    for policy in iam.list_role_policies(RoleName="hotel-release-exec")["PolicyNames"]:
        iam.delete_role_policy(RoleName="hotel-release-exec", PolicyName=policy)
    iam.delete_role(RoleName="hotel-release-exec")
except iam.exceptions.NoSuchEntityException:
    pass
print("endpoint, registry entries, alarms, release files, the endpoint's role and the GitHub user deleted")
