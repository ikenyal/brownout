#!/usr/bin/env bash
# Remove everything Brownout created, in an order that avoids dependency errors:
#   1. the trigger (no new alerts reach the agent)
#   2. the AgentCore Runtime and its stack
#   3. the edge (CloudFront, Function, KeyValueStore, S3)
# Usage: AWS_PROFILE=... BROWNOUT_NAME=brownouttest scripts/teardown.sh
# Not removed: the CDK bootstrap stack (CDKToolkit), which other CDK apps in the account may share.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="npx -y @aws/agentcore@1.0.0"
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
NAME="${BROWNOUT_NAME:-brownout}"
PROJECT="$ROOT/deploy/${NAME}rt"

read -r -p "Delete every AWS resource of '$NAME'? Type the name to confirm: " answer
[ "$answer" = "$NAME" ] || { echo "cancelled"; exit 1; }

cd "$ROOT"
uv run python infra/teardown.py trigger --yes
if [ -f "$PROJECT/agentcore/agentcore.json" ]; then
  (cd "$PROJECT" && $CLI remove all --yes && $CLI deploy --yes)
fi
uv run python infra/teardown.py edge --yes
echo "done. Check the AWS console (CloudFront, AgentCore, S3) if you want to be sure."
