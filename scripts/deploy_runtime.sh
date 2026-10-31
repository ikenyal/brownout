#!/usr/bin/env bash
# Stage the Brownout runtime into the AgentCore project and deploy it.
# Usage: AWS_PROFILE=... scripts/deploy_runtime.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/deploy/brownoutrt/app/Brownout"
CLI="npx -y @aws/agentcore@1.0.0"

rm -rf "$APP/brownout" "$APP/content"
mkdir -p "$APP/brownout"
cp "$ROOT/runtime/main.py" "$APP/main.py"
cp "$ROOT"/brownout/{__init__,agent,facts,edge}.py "$APP/brownout/"
cp -r "$ROOT/content" "$APP/content"

cd "$APP"
if [ ! -f pyproject.toml ]; then
  uv init --bare --no-workspace --name brownout-runtime --python 3.13 >/dev/null
  sed -i '' 's/^requires-python = .*/requires-python = ">=3.13,<3.14"/' pyproject.toml
  uv add strands-agents bedrock-agentcore aws-opentelemetry-distro boto3 'botocore[crt]' >/dev/null
fi

cd "$ROOT/deploy/brownoutrt"
# agentcore.json refers to ../../infra/runtime-policy.json, resolved from agentcore/cdk
mkdir -p infra && cp "$ROOT/infra/runtime-policy.json" infra/
$CLI deploy
