"""Create (or reuse) the Brownout edge: S3 + CloudFront + KeyValueStore + Function.

Idempotent: safe to run again. Saves IDs to infra/outputs.json.
Run:  AWS_PROFILE=... uv run python infra/deploy_infra.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs.json"
REGION = "us-east-1"
NAME = "brownout"

sts = boto3.client("sts", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
cf = boto3.client("cloudfront", region_name=REGION)
ACCOUNT = sts.get_caller_identity()["Account"]
BUCKET = f"{NAME}-site-{ACCOUNT}"


def load() -> dict:
    return json.loads(OUTPUTS.read_text()) if OUTPUTS.exists() else {}


def save(out: dict) -> None:
    OUTPUTS.write_text(json.dumps(out, indent=2))


def bucket(out: dict) -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
    except s3.exceptions.ClientError:
        s3.create_bucket(Bucket=BUCKET)
        s3.put_public_access_block(Bucket=BUCKET, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    out["bucket"] = BUCKET


def kvs(out: dict) -> None:
    if "kvs_arn" in out:
        return
    res = cf.create_key_value_store(Name=f"{NAME}-state", Comment="Brownout alert level")
    out["kvs_arn"] = res["KeyValueStore"]["ARN"]
    while cf.describe_key_value_store(Name=f"{NAME}-state")["KeyValueStore"]["Status"] != "READY":
        time.sleep(3)


def function(out: dict) -> None:
    fname = f"{NAME}-router"
    code = (HERE / "router.js").read_bytes()
    config = {"Comment": "Brownout router", "Runtime": "cloudfront-js-2.0",
              "KeyValueStoreAssociations": {"Quantity": 1, "Items": [{"KeyValueStoreARN": out["kvs_arn"]}]}}
    try:
        etag = cf.describe_function(Name=fname, Stage="DEVELOPMENT")["ETag"]
        etag = cf.update_function(Name=fname, IfMatch=etag, FunctionConfig=config, FunctionCode=code)["ETag"]
    except cf.exceptions.NoSuchFunctionExists:
        etag = cf.create_function(Name=fname, FunctionConfig=config, FunctionCode=code)["ETag"]
    res = cf.publish_function(Name=fname, IfMatch=etag)
    out["function_arn"] = res["FunctionSummary"]["FunctionMetadata"]["FunctionARN"]


def distribution(out: dict) -> None:
    if "distribution_id" in out:
        return
    oac = cf.create_origin_access_control(OriginAccessControlConfig={
        "Name": f"{NAME}-oac", "Description": "Brownout S3 access", "SigningProtocol": "sigv4",
        "SigningBehavior": "always", "OriginAccessControlOriginType": "s3"})["OriginAccessControl"]["Id"]
    res = cf.create_distribution(DistributionConfig={
        "CallerReference": f"{NAME}-{int(time.time())}",
        "Comment": "Brownout - Example City (fictional)",
        "Enabled": True,
        "DefaultRootObject": "",
        "Origins": {"Quantity": 1, "Items": [{
            "Id": "site", "DomainName": f"{BUCKET}.s3.{REGION}.amazonaws.com",
            "S3OriginConfig": {"OriginAccessIdentity": ""}, "OriginAccessControlId": oac}]},
        "DefaultCacheBehavior": {
            "TargetOriginId": "site", "ViewerProtocolPolicy": "redirect-to-https", "Compress": True,
            "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",  # Managed-CachingOptimized
            "FunctionAssociations": {"Quantity": 1, "Items": [
                {"FunctionARN": out["function_arn"], "EventType": "viewer-request"}]}},
        "PriceClass": "PriceClass_All",
    })["Distribution"]
    out["distribution_id"], out["domain"] = res["Id"], res["DomainName"]
    out["distribution_arn"] = res["ARN"]
    s3.put_bucket_policy(Bucket=BUCKET, Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "cloudfront.amazonaws.com"},
        "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{BUCKET}/*",
        "Condition": {"StringEquals": {"AWS:SourceArn": res["ARN"]}}}]}))


def main() -> None:
    out = load()
    bucket(out); save(out)
    kvs(out); save(out)
    function(out); save(out)
    distribution(out); save(out)
    runtime_policy(out)
    print(json.dumps(out, indent=2))


def runtime_policy(out: dict) -> None:
    """Least-privilege extras for the AgentCore Runtime role (used by scripts/deploy_runtime.sh)."""
    policy = {"Version": "2012-10-17", "Statement": [
        {"Sid": "PublishLitePages", "Effect": "Allow", "Action": ["s3:PutObject"],
         "Resource": f"arn:aws:s3:::{out['bucket']}/level-*"},
        {"Sid": "FlipMode", "Effect": "Allow", "Resource": out["kvs_arn"],
         "Action": ["cloudfront-keyvaluestore:DescribeKeyValueStore",
                    "cloudfront-keyvaluestore:GetKey", "cloudfront-keyvaluestore:PutKey"]},
        {"Sid": "NovaModels", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": ["arn:aws:bedrock:*::foundation-model/amazon.nova-*",
                      "arn:aws:bedrock:*:*:inference-profile/us.amazon.nova-*"]}]}
    (HERE / "runtime-policy.json").write_text(json.dumps(policy, indent=2))


if __name__ == "__main__":
    main()
