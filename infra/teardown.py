"""Delete what deploy_infra.py and deploy_trigger.py created, in dependency order.

Run:  AWS_PROFILE=... uv run python infra/teardown.py trigger   # EventBridge rule, Lambda, its role and logs
      AWS_PROFILE=... uv run python infra/teardown.py edge      # CloudFront, Function, KeyValueStore, OAC, S3,
                                                                # and the AgentCore Runtime's log groups
Most people run scripts/teardown.sh, which also removes the AgentCore Runtime in between.

Every step checks first and skips what is already gone, so it is safe to run again.
Disabling a CloudFront distribution takes several minutes; the script waits for it.
"""

from __future__ import annotations

import json
import sys

import boto3
from botocore.exceptions import ClientError

from naming import IS_DEFAULT, NAME, OUTPUTS, RUNTIME_POLICY, TRIGGER

REGION = "us-east-1"


def gone(e: ClientError) -> bool:
    code = e.response["Error"]["Code"]
    return code in {"ResourceNotFoundException", "NoSuchEntity", "NoSuchDistribution", "NoSuchFunctionExists",
                    "NoSuchOriginAccessControl", "EntityNotFound", "NoSuchBucket", "404"}


def step(label: str, fn) -> None:
    try:
        fn()
        print(f"deleted: {label}")
    except ClientError as e:
        if not gone(e):
            raise
        print(f"already gone: {label}")


def teardown_trigger() -> None:
    ev = boto3.client("events", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    iam = boto3.client("iam")
    logs = boto3.client("logs", region_name=REGION)

    def rule() -> None:
        ev.remove_targets(Rule=TRIGGER, Ids=["lambda"])
        ev.delete_rule(Name=TRIGGER)

    def role() -> None:
        for p in iam.list_role_policies(RoleName=TRIGGER)["PolicyNames"]:
            iam.delete_role_policy(RoleName=TRIGGER, PolicyName=p)
        for p in iam.list_attached_role_policies(RoleName=TRIGGER)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=TRIGGER, PolicyArn=p["PolicyArn"])
        iam.delete_role(RoleName=TRIGGER)

    step(f"EventBridge rule {TRIGGER}", rule)  # stop new alerts first
    step(f"Lambda {TRIGGER}", lambda: lam.delete_function(FunctionName=TRIGGER))
    step(f"IAM role {TRIGGER}", role)
    step(f"log group /aws/lambda/{TRIGGER}", lambda: logs.delete_log_group(logGroupName=f"/aws/lambda/{TRIGGER}"))


def teardown_edge(out: dict) -> None:
    cf = boto3.client("cloudfront", region_name=REGION)
    s3 = boto3.resource("s3", region_name=REGION)

    def distribution() -> None:
        dist_id = out["distribution_id"]
        res = cf.get_distribution_config(Id=dist_id)
        config, etag = res["DistributionConfig"], res["ETag"]
        if config["Enabled"]:
            config["Enabled"] = False
            etag = cf.update_distribution(Id=dist_id, IfMatch=etag, DistributionConfig=config)["ETag"]
        print("waiting for the distribution to be disabled (often 5-15 minutes)...")
        cf.get_waiter("distribution_deployed").wait(Id=dist_id, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
        cf.delete_distribution(Id=dist_id, IfMatch=cf.get_distribution(Id=dist_id)["ETag"])

    def oac() -> None:
        items = cf.list_origin_access_controls()["OriginAccessControlList"].get("Items", [])
        match = [i for i in items if i["Name"] == f"{NAME}-oac"]
        if not match:
            raise ClientError({"Error": {"Code": "NoSuchOriginAccessControl"}}, "ListOriginAccessControls")
        oac_id = match[0]["Id"]
        cf.delete_origin_access_control(Id=oac_id, IfMatch=cf.get_origin_access_control(Id=oac_id)["ETag"])

    def function() -> None:
        fname = f"{NAME}-router"
        cf.delete_function(Name=fname, IfMatch=cf.describe_function(Name=fname)["ETag"])

    def kvs() -> None:
        kname = f"{NAME}-state"
        cf.delete_key_value_store(Name=kname, IfMatch=cf.describe_key_value_store(Name=kname)["ETag"])

    def bucket() -> None:
        b = s3.Bucket(out["bucket"])
        b.objects.all().delete()
        b.delete()

    # The function cannot go while a distribution uses it, and the KeyValueStore cannot go while
    # the function is associated with it, so the order matters.
    if "distribution_id" in out:
        step(f"CloudFront distribution {out['distribution_id']}", distribution)
    step(f"origin access control {NAME}-oac", oac)
    step(f"CloudFront Function {NAME}-router", function)
    step(f"KeyValueStore {NAME}-state", kvs)
    if "bucket" in out:
        step(f"S3 bucket {out['bucket']}", bucket)

    # Removing the AgentCore stack leaves the runtime's log group behind. Its name starts with
    # "<project>_<target>_<runtime>-<id>", and the project is "<NAME>rt", so this prefix
    # never matches another copy (brownoutrt_ vs brownouttestrt_).
    logs = boto3.client("logs", region_name=REGION)
    prefix = f"/aws/bedrock-agentcore/runtimes/{NAME}rt_"
    for page in logs.get_paginator("describe_log_groups").paginate(logGroupNamePrefix=prefix):
        for group in page["logGroups"]:
            name = group["logGroupName"]
            step(f"log group {name}", lambda name=name: logs.delete_log_group(logGroupName=name))


def main(part: str, yes: bool) -> None:
    if not OUTPUTS.exists():
        raise SystemExit(f"{OUTPUTS.name} not found: nothing was deployed under the name {NAME!r}.")
    out = json.loads(OUTPUTS.read_text())
    if not yes:
        warn = " (the default name: this is the main demo)" if IS_DEFAULT else ""
        if input(f"Delete the {part} resources of {NAME!r}{warn}? Type the name to confirm: ") != NAME:
            raise SystemExit("cancelled")
    if part in ("trigger", "all"):
        teardown_trigger()
    if part in ("edge", "all"):
        teardown_edge(out)
        OUTPUTS.unlink()
        RUNTIME_POLICY.unlink(missing_ok=True)
        print(f"removed {OUTPUTS.name}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--yes"]
    if len(args) != 1 or args[0] not in ("trigger", "edge", "all"):
        raise SystemExit("usage: teardown.py trigger|edge|all [--yes]")
    main(args[0], "--yes" in sys.argv)
