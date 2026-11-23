"""Names and clients every release script shares. Imported, never run."""
import os

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "us-west-2")
session = boto3.Session(region_name=REGION)
sm = session.client("sagemaker")                  # the registry, models and endpoints
runtime = session.client("sagemaker-runtime")     # sending bookings to the endpoint
s3 = session.client("s3")
ACCOUNT = session.client("sts").get_caller_identity()["Account"]

GROUP = "hotel-release-group"                     # the model group in the registry
ENDPOINT = "hotel-release-endpoint"                        # the endpoint callers use
INSTANCES = 2                                     # machines behind it, so one can be the canary
ALARMS = ["hotel-release-errors", "hotel-release-latency"]  # either one going off during a release rolls it back
BUCKET = f"hotel-release-bucket"          # model files go under hotel/releases/<commit>/
EXEC_ROLE = f"arn:aws:iam::835997719250:role/hotel-release-role"  # the role the endpoint runs as
# AWS's own XGBoost container, the one both earlier models were trained with
IMAGE = f"246618743249.dkr.ecr.us-west-2.amazonaws.com/sagemaker-xgboost:1.7-1"


def package_arn(version):
    """The ARN of one version in the group."""
    return f"arn:aws:sagemaker:{REGION}:{ACCOUNT}:model-package/{GROUP}/{version}"


def exists(describe, **name):
    """True when a describe call finds the thing. SageMaker answers ValidationException when it does not."""
    try:
        describe(**name)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationException":
            return False
        raise
