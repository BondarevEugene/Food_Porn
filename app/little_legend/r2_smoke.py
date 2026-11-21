"""One-shot private R2 smoke test; no customer assets, secrets or public URLs.

Run in the Railway service environment:
    python -m app.little_legend.r2_smoke --live

The test uploads a small random probe to an isolated diagnostics prefix,
reads it back, then deletes it. It never touches existing book objects.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
from dataclasses import dataclass

PREFIX = "little-legend/diagnostics/"


@dataclass(frozen=True)
class StorageTarget:
    label: str
    endpoint: str
    bucket: str
    region: str
    access: str
    secret: str


def targets_from_environment() -> list[StorageTarget]:
    common = StorageTarget(
        label="release",
        endpoint=os.getenv("LITTLE_LEGEND_S3_ENDPOINT_URL", ""),
        bucket=os.getenv("LITTLE_LEGEND_S3_BUCKET", ""),
        region=os.getenv("LITTLE_LEGEND_S3_REGION", ""),
        access=os.getenv("LITTLE_LEGEND_S3_ACCESS_KEY_ID", ""),
        secret=os.getenv("LITTLE_LEGEND_S3_SECRET_ACCESS_KEY", ""),
    )
    art = StorageTarget(
        label="art",
        endpoint=os.getenv("LITTLE_LEGEND_ART_S3_ENDPOINT", ""),
        bucket=os.getenv("LITTLE_LEGEND_ART_S3_BUCKET", ""),
        region=os.getenv("LITTLE_LEGEND_ART_S3_REGION", ""),
        access=os.getenv("LITTLE_LEGEND_ART_S3_ACCESS_KEY", ""),
        secret=os.getenv("LITTLE_LEGEND_ART_S3_SECRET_KEY", ""),
    )
    return [common, art]


def validate_target(target: StorageTarget) -> None:
    if not target.endpoint.startswith("https://") or not all((
        target.bucket, target.region, target.access, target.secret,
    )):
        raise ValueError(f"{target.label}: missing or invalid private S3 settings")


def probe_target(target: StorageTarget, *, client=None) -> None:
    """Verify put/get/delete and always attempt cleanup after upload."""
    validate_target(target)
    if client is None:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=target.endpoint,
            region_name=target.region,
            aws_access_key_id=target.access,
            aws_secret_access_key=target.secret,
            config=Config(
                connect_timeout=5, read_timeout=10,
                retries={"max_attempts": 2},
            ),
        )
    key = PREFIX + secrets.token_hex(20) + ".bin"
    payload = secrets.token_bytes(96)
    written = False
    try:
        # Set cleanup flag before dispatch: an ambiguous timeout may still
        # mean that the provider accepted the object.
        written = True
        client.put_object(
            Bucket=target.bucket, Key=key, Body=payload,
            ContentType="application/octet-stream",
            CacheControl="private, no-store",
        )
        response = client.get_object(Bucket=target.bucket, Key=key)
        body = response["Body"]
        try:
            received = body.read(97)
        finally:
            body.close()
        if hashlib.sha256(received).digest() != hashlib.sha256(payload).digest():
            raise RuntimeError("Probe content integrity check failed")
    finally:
        if written:
            client.delete_object(Bucket=target.bucket, Key=key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private Little Legend R2 probe")
    parser.add_argument(
        "--live", action="store_true",
        help="Perform a real put/get/delete cycle against configured private R2",
    )
    args = parser.parse_args(argv)
    targets = targets_from_environment()
    for target in targets:
        try:
            validate_target(target)
        except ValueError:
            print(f"{target.label}: CONFIG_MISSING")
            return 2
    if not args.live:
        print("release: CONFIG_OK")
        print("art: CONFIG_OK")
        print("No network requests made. Pass --live to run the R2 smoke test.")
        return 0
    for target in targets:
        try:
            probe_target(target)
        except Exception:
            # Avoid printing exception strings: provider errors can include
            # bucket names, endpoint URLs or credential-related metadata.
            print(f"{target.label}: PROBE_FAILED")
            return 1
        print(f"{target.label}: PROBE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
