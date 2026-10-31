"""AWS side of Brownout: publish pages to S3 and flip the mode in CloudFront KeyValueStore."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Callable

import boto3

REGION = "us-east-1"
OUTPUTS = Path(__file__).resolve().parents[1] / "infra" / "outputs.json"


def config() -> dict:
    """IDs come from env vars on AgentCore Runtime, or infra/outputs.json locally."""
    if os.environ.get("BROWNOUT_BUCKET"):
        return {"bucket": os.environ["BROWNOUT_BUCKET"], "kvs_arn": os.environ["BROWNOUT_KVS_ARN"]}
    return json.loads(OUTPUTS.read_text())


def s3_publisher() -> Callable[[int, str], str]:
    s3 = boto3.client("s3", region_name=REGION)
    bucket = config()["bucket"]

    def publish(level: int, html: str) -> str:
        key = f"level-{level}/index.html"
        s3.put_object(Bucket=bucket, Key=key, Body=html.encode("utf-8"),
                      ContentType="text/html; charset=utf-8", CacheControl="max-age=30")
        return f"Published s3://{bucket}/{key}"
    return publish


def set_level(level: int) -> None:
    """The only thing that switches the live site. Takes effect at the edge within seconds."""
    kvs = boto3.client("cloudfront-keyvaluestore", region_name=REGION)
    arn = config()["kvs_arn"]
    etag = kvs.describe_key_value_store(KvsARN=arn)["ETag"]
    kvs.put_key(KvsARN=arn, Key="level", Value=str(level), IfMatch=etag)


def get_level() -> int:
    kvs = boto3.client("cloudfront-keyvaluestore", region_name=REGION)
    try:
        return int(kvs.get_key(KvsARN=config()["kvs_arn"], Key="level")["Value"])
    except kvs.exceptions.ResourceNotFoundException:
        return 1


def upload_dir(local: Path, prefix: str) -> int:
    s3 = boto3.client("s3", region_name=REGION)
    bucket, n = config()["bucket"], 0
    for p in sorted(local.rglob("*")):
        if p.is_file():
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            s3.upload_file(str(p), bucket, f"{prefix}/{p.relative_to(local)}",
                           ExtraArgs={"ContentType": ctype, "CacheControl": "max-age=3600"})
            n += 1
    return n
