"""Put candidate/model.tar.gz into S3 and register it as the next version of the
model group, waiting for approval. Prints the new version number.

    python release/register.py
"""
import os
import subprocess
from pathlib import Path

from config import BUCKET, GROUP, IMAGE, exists, s3, sm

ROOT = Path(__file__).resolve().parent.parent
sha = os.environ.get("GITHUB_SHA") or subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
source = "local"
if os.environ.get("GITHUB_RUN_ID"):
    source = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

# The group is made the first time and found every time after
if not exists(sm.describe_model_package_group, ModelPackageGroupName=GROUP):
    sm.create_model_package_group(
        ModelPackageGroupName=GROUP,
        ModelPackageGroupDescription="Predicts whether a hotel booking will be cancelled")

key = f"hotel/releases/{sha}/model.tar.gz"
s3.upload_file(str(ROOT / "candidate/model.tar.gz"), BUCKET, key)

response = sm.create_model_package(
    ModelPackageGroupName=GROUP,
    ModelApprovalStatus="PendingManualApproval",
    ModelPackageDescription=f"Candidate from commit {sha[:7]}",
    CustomerMetadataProperties={"git_sha": sha, "source": source},
    InferenceSpecification={
        "Containers": [{"Image": IMAGE, "ModelDataUrl": f"s3://{BUCKET}/{key}"}],
        "SupportedContentTypes": ["text/csv"],
        "SupportedResponseMIMETypes": ["text/csv"],
    },
)
version = response["ModelPackageArn"].rsplit("/", 1)[1]
print(f"registered {GROUP} version {version}, status PendingManualApproval")

if os.environ.get("GITHUB_OUTPUT"):              # hands the number to the deploy job
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"version={version}\n")
