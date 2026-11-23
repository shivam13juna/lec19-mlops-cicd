"""Approve one registered version, put it on the endpoint, and mark it Production.
The same script rolls back: give it an older version.

    python release/deploy.py VERSION
    python release/deploy.py VERSION --rollback

--rollback marks the version it replaces Rejected instead of leaving it approved, and moves
all the traffic at once, because it is going back to a version that was live before.
"""
import argparse
import getpass
import os
import sys
import time

from config import ALARMS, ENDPOINT, EXEC_ROLE, GROUP, INSTANCES, exists, package_arn, sm

parser = argparse.ArgumentParser()
parser.add_argument("version")
parser.add_argument("--rollback", action="store_true")
args = parser.parse_args()
version, arn, name = args.version, package_arn(args.version), f"hotel-release-v{args.version}"
started = time.time()

status = sm.describe_model_package(ModelPackageName=arn)["ModelApprovalStatus"]
print(f"version {version} is {status}")

# Approving is the decision. Everything below runs only for an approved version.
sm.update_model_package(
    ModelPackageArn=arn, ModelApprovalStatus="Approved",
    ApprovalDescription=f"Released by {os.environ.get('GITHUB_ACTOR') or getpass.getuser()}")

if not exists(sm.describe_model, ModelName=name):
    sm.create_model(ModelName=name, ExecutionRoleArn=EXEC_ROLE,
                    PrimaryContainer={"ModelPackageName": arn})
if not exists(sm.describe_endpoint_config, EndpointConfigName=name):
    sm.create_endpoint_config(
        EndpointConfigName=name,
        ProductionVariants=[{"VariantName": "AllTraffic", "ModelName": name,
                             "InstanceType": "ml.m5.large", "InitialInstanceCount": INSTANCES}])

# Blue/green. The new model starts on its own machines (green) beside the old ones (blue).
# A release sends one machine's share of the traffic to green first, the canary, and waits
# while the alarms watch it. Then green takes everything, and blue is kept for a while
# before it is removed. If an alarm goes off before the end, SageMaker moves all the
# traffic back to blue by itself.
if args.rollback:
    routing = {"Type": "ALL_AT_ONCE", "WaitIntervalInSeconds": 0}
else:
    routing = {"Type": "CANARY", "CanarySize": {"Type": "INSTANCE_COUNT", "Value": 1},
               "WaitIntervalInSeconds": 300}
deployment_config = {
    "BlueGreenUpdatePolicy": {"TrafficRoutingConfiguration": routing,
                              "TerminationWaitInSeconds": 120,
                              "MaximumExecutionTimeoutInSeconds": 1800},
    "AutoRollbackConfiguration": {"Alarms": [{"AlarmName": a} for a in ALARMS]},
}

if exists(sm.describe_endpoint, EndpointName=ENDPOINT):
    sm.update_endpoint(EndpointName=ENDPOINT, EndpointConfigName=name,
                       DeploymentConfig=deployment_config)
    print(f"updating {ENDPOINT} to version {version}")
else:
    sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=name)
    print(f"creating {ENDPOINT} with version {version}")
sm.get_waiter("endpoint_in_service").wait(EndpointName=ENDPOINT)
print(f"{ENDPOINT} in service after {time.time() - started:.0f}s")

# In service does not mean this version. After an automatic rollback the endpoint is
# in service again, on the old model, so ask which configuration it is running.
endpoint = sm.describe_endpoint(EndpointName=ENDPOINT)
if endpoint["EndpointConfigName"] != name:
    reason = endpoint.get("FailureReason", "")
    print(f"rolled back: {ENDPOINT} is still running {endpoint['EndpointConfigName']}")
    print(f"reason: {reason}")
    sm.update_model_package(ModelPackageArn=arn, ModelApprovalStatus="Rejected",
                            ApprovalDescription=f"Rolled back during the release: {reason[:900]}")
    print(f"version {version} marked Rejected")
    sys.exit(1)

# The registry follows the endpoint, never the other way round
for page in sm.get_paginator("list_model_packages").paginate(
    ModelPackageGroupName=GROUP
):
    for summary in page["ModelPackageSummaryList"]:
        other = str(summary["ModelPackageVersion"])

        if other != version and summary.get("ModelLifeCycle", {}).get("Stage") == "Production":

            params = {
                "ModelPackageArn": summary["ModelPackageArn"],
                "ModelLifeCycle": {
                    "Stage": "Archived",
                    "StageStatus": "Approved",
                    "StageDescription": f"Replaced by version {version}"
                }
            }

            if args.rollback:
                params["ModelApprovalStatus"] = "Rejected"
                params["ApprovalDescription"] = f"Rolled back to version {version}"

            sm.update_model_package(**params)

            print(f"version {other} archived")
sm.update_model_package(
    ModelPackageArn=arn,
    ModelLifeCycle={"Stage": "Production", "StageStatus": "Approved",
                    "StageDescription": f"Serving on {ENDPOINT}"})
print(f"version {version} is Production")
