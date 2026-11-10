"""AWS side of Brownout: publish pages to S3 and flip the mode in CloudFront KeyValueStore."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Callable

import boto3

REGION = "us-east-1"
NAME = os.environ.get("BROWNOUT_NAME", "brownout")
OUTPUTS = Path(__file__).resolve().parents[1] / "infra" / (
    "outputs.json" if NAME == "brownout" else f"outputs-{NAME}.json")
EVENT_SOURCE = "examplecity.alerts" if NAME == "brownout" else f"examplecity.alerts.{NAME}"


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


def set_level(level: int, issued_at: str | None = None) -> bool:
    """The only thing that switches the live site. Takes effect at the edge within seconds.

    issued_at is the alert's own timestamp (EventBridge "time", ISO 8601 UTC). Runs can finish
    out of order: a slow or retried run for an older alert must not overwrite a newer level.
    So the write is a compare-and-set: read the store's ETag, read the timestamp of the level
    that is live now, and write level and timestamp together only if ours is not older.
    If anything wrote in between, the ETag no longer matches, the write is rejected, and we
    read again. Returns False if the alert is stale and nothing was written.
    """
    kvs = boto3.client("cloudfront-keyvaluestore", region_name=REGION)
    arn = config()["kvs_arn"]
    for _ in range(5):
        etag = kvs.describe_key_value_store(KvsARN=arn)["ETag"]
        if issued_at is not None and (current := live_issued_at(kvs, arn)) and current > issued_at:
            return False
        puts = [{"Key": "level", "Value": str(level)}]
        if issued_at is not None:
            puts.append({"Key": "issued_at", "Value": issued_at})
        try:
            kvs.update_keys(KvsARN=arn, IfMatch=etag, Puts=puts)
            return True
        except kvs.exceptions.ConflictException:
            continue  # someone else wrote first; read again
    raise RuntimeError("KeyValueStore kept changing under us; giving up after 5 attempts")


def live_issued_at(kvs=None, arn: str | None = None) -> str | None:
    kvs = kvs or boto3.client("cloudfront-keyvaluestore", region_name=REGION)
    try:
        return kvs.get_key(KvsARN=arn or config()["kvs_arn"], Key="issued_at")["Value"]
    except kvs.exceptions.ResourceNotFoundException:
        return None


def is_stale(issued_at: str | None) -> bool:
    """True if a newer alert than this one has already switched the site."""
    current = live_issued_at() if issued_at else None
    return bool(current and current > issued_at)


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
