#!/usr/bin/env bash
# Makes the gate a rule: main takes changes only through a pull request whose
# `gate` check has passed. Without it the gate reports a result that nobody has to obey.
#
#     infra/protect.sh
#
# Needs the GitHub CLI signed in as the owner of this repository.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=$(git remote get-url origin | sed -E 's#\.git$##; s#^.*[:/]([^/:]+/[^/]+)$#\1#')
gh api -X POST "repos/$REPO/rulesets" --input - >/dev/null <<'JSON'
{"name": "main needs the gate", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
 "rules": [
  {"type": "pull_request", "parameters": {"required_approving_review_count": 0,
     "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false,
     "require_last_push_approval": false, "required_review_thread_resolution": false}},
  {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
     "required_status_checks": [{"context": "gate"}]}}]}
JSON
echo "ruleset created on $REPO: main needs a pull request and a passing gate"
