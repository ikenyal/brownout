"""Wire EventBridge to the Brownout runtime.

An "AlertLevelChanged" event (source "examplecity.alerts") -> Lambda -> AgentCore
Runtime. The Lambda is a thin adapter: EventBridge cannot target a runtime directly.
Run:  uv run python infra/deploy_trigger.py <runtime-arn>
"""

from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import boto3

REGION = "us-east-1"
OUTPUTS = Path(__file__).resolve().parent / "outputs.json"
NAME = "brownout-trigger"

HANDLER = '''
import json, os, uuid, boto3
client = boto3.client("bedrock-agentcore")
def handler(event, context):
    d = event["detail"]
    payload = {"hazard": d["hazard"], "level": int(d["level"])}
    res = client.invoke_agent_runtime(
        agentRuntimeArn=os.environ["RUNTIME_ARN"],
        runtimeSessionId=f"alert-{uuid.uuid4()}",
        payload=json.dumps(payload).encode(),
    )
    body = b"".join(res["response"]).decode()
    print(json.dumps({"payload": payload, "result": body}))
    return body
'''


def main(runtime_arn: str) -> None:
    out = json.loads(OUTPUTS.read_text())
    iam = boto3.client("iam")
    lam = boto3.client("lambda", region_name=REGION)
    ev = boto3.client("events", region_name=REGION)

    try:
        role_arn = iam.get_role(RoleName=NAME)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        role_arn = iam.create_role(RoleName=NAME, AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17", "Statement": [{"Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}))["Role"]["Arn"]
        iam.attach_role_policy(RoleName=NAME, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        time.sleep(10)
    iam.put_role_policy(RoleName=NAME, PolicyName="invoke-runtime", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "bedrock-agentcore:InvokeAgentRuntime",
        "Resource": [runtime_arn, f"{runtime_arn}/*"]}]}))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("index.py", HANDLER)
    env = {"Variables": {"RUNTIME_ARN": runtime_arn}}
    try:
        fn = lam.create_function(FunctionName=NAME, Runtime="python3.13", Role=role_arn, Handler="index.handler",
                                 Code={"ZipFile": buf.getvalue()}, Timeout=300, Environment=env)
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=NAME, ZipFile=buf.getvalue())
        lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        fn = lam.update_function_configuration(FunctionName=NAME, Environment=env, Timeout=300)
    fn_arn = fn["FunctionArn"]

    rule_arn = ev.put_rule(Name=NAME, EventPattern=json.dumps({
        "source": ["examplecity.alerts"], "detail-type": ["AlertLevelChanged"]}))["RuleArn"]
    ev.put_targets(Rule=NAME, Targets=[{"Id": "lambda", "Arn": fn_arn}])
    try:
        lam.add_permission(FunctionName=NAME, StatementId="eventbridge", Action="lambda:InvokeFunction",
                           Principal="events.amazonaws.com", SourceArn=rule_arn)
    except lam.exceptions.ResourceConflictException:
        pass
    out.update({"runtime_arn": runtime_arn, "trigger_function": fn_arn, "trigger_rule": rule_arn})
    OUTPUTS.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
