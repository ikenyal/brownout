#!/usr/bin/env bash
# Create (first time only) the AgentCore project, stage the Brownout runtime into it, and deploy.
# Run infra/deploy_infra.py first: the runtime needs the bucket, the KeyValueStore and the policy it writes.
# Usage: AWS_PROFILE=... scripts/deploy_runtime.sh
#        AWS_PROFILE=... BROWNOUT_NAME=brownouttest scripts/deploy_runtime.sh   # a second, independent copy
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="npx -y @aws/agentcore@1.0.0"
# Everything in Brownout lives in us-east-1. Without this, the AgentCore CLI creates its deployment
# target in the profile's default region, and the us-east-1 trigger Lambda cannot reach the runtime.
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
NAME="${BROWNOUT_NAME:-brownout}"
if [ "$NAME" = "brownout" ]; then
  RUNTIME="Brownout"; OUT="$ROOT/infra/outputs.json"; POLICY="$ROOT/infra/runtime-policy.json"
else
  RUNTIME="$NAME"; OUT="$ROOT/infra/outputs-$NAME.json"; POLICY="$ROOT/infra/runtime-policy-$NAME.json"
fi
PROJECT="$ROOT/deploy/${NAME}rt"
APP="$PROJECT/app/$RUNTIME"
[ -f "$OUT" ] || { echo "$OUT not found: run infra/deploy_infra.py first" >&2; exit 1; }

if [ ! -f "$PROJECT/agentcore/agentcore.json" ]; then
  # agentcore.json holds account-specific values, so it is not in git. Generate it.
  ENV_VARS="$(python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print(json.dumps({"BROWNOUT_BUCKET": o["bucket"], "BROWNOUT_KVS_ARN": o["kvs_arn"], "BROWNOUT_AGENT": sys.argv[2]}))' "$OUT" "${BROWNOUT_AGENT:-on}")"
  TMP="$(mktemp -d)"
  (cd "$TMP" && $CLI create --name "${NAME}rt" --template empty --skip-git --skip-install \
     && cd "${NAME}rt" && $CLI add runtime --name "$RUNTIME" --language python \
        --environment-variables "$ENV_VARS" --additional-policies "$POLICY")
  if [ -d "$PROJECT" ]; then
    # The default project's scaffold is already in git; only the generated config is missing.
    cp "$TMP/${NAME}rt/agentcore/agentcore.json" "$TMP/${NAME}rt/agentcore/aws-targets.json" "$PROJECT/agentcore/"
  else
    mkdir -p "$ROOT/deploy" && cp -R "$TMP/${NAME}rt" "$PROJECT"
  fi
  rm -rf "$TMP"
fi

rm -rf "$APP/brownout" "$APP/content"
mkdir -p "$APP/brownout"
cp "$ROOT/runtime/main.py" "$APP/main.py"
cp "$ROOT"/brownout/{__init__,agent,facts,edge,template}.py "$APP/brownout/"
cp -r "$ROOT/content" "$APP/content"

cd "$APP"
if [ ! -f pyproject.toml ]; then
  uv init --bare --no-workspace --name brownout-runtime --python 3.13 >/dev/null
  # Pin below 3.14 so the CLI keeps the PYTHON_3_13 runtime (portable: no sed -i).
  python3 - <<'PY'
import re, pathlib
p = pathlib.Path("pyproject.toml")
p.write_text(re.sub(r"(?m)^requires-python = .*$", 'requires-python = ">=3.13,<3.14"', p.read_text()))
PY
  uv add strands-agents bedrock-agentcore aws-opentelemetry-distro boto3 'botocore[crt]' >/dev/null
fi

cd "$PROJECT"
# agentcore create ran with --skip-install, so install the CDK app's dependencies once.
[ -d agentcore/cdk/node_modules ] || (cd agentcore/cdk && npm install)
# The original project's agentcore.json refers to ../../infra/runtime-policy.json, resolved from agentcore/cdk
mkdir -p infra && cp "$POLICY" infra/
$CLI deploy
