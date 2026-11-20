"""Little Legend Railway deployment contract, safe for CI and operators.

This module does not connect to Railway, Neon, Telegram, S3 or OpenAI.
It verifies the four independent service commands and their opt-in settings.
"""
from __future__ import annotations

import argparse
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceContract:
    name: str
    config: str
    command: str
    required: tuple[str, ...]
    enabled: tuple[str, ...] = ()


SERVICES = (
    ServiceContract(
        "conductor", "railway.little-legend-conductor.toml",
        "python -m app.little_legend.production_conductor",
        ("DATABASE_URL", "LL_ILLUSTRATION_PRICE_MICRO_USD"),
        ("LL_CONDUCTOR_ENABLED",),
    ),
    ServiceContract(
        "writer", "railway.little-legend-writer.toml",
        "python -m app.little_legend.ai_production_runner --mode writer",
        ("DATABASE_URL", "OPENAI_API_KEY"),
        ("LL_AI_PRODUCTION_ENABLED", "LL_WRITER_ENABLED",
         "LL_TEXT_AI_CONSENT_ENABLED"),
    ),
    ServiceContract(
        "illustration", "railway.little-legend-illustration.toml",
        "python -m app.little_legend.ai_production_runner --mode illustration",
        ("DATABASE_URL", "OPENAI_API_KEY", "LL_ILLUSTRATION_PRICE_MICRO_USD",
         "LITTLE_LEGEND_ART_S3_ENDPOINT", "LITTLE_LEGEND_ART_S3_BUCKET",
         "LITTLE_LEGEND_ART_S3_REGION", "LITTLE_LEGEND_ART_S3_ACCESS_KEY",
         "LITTLE_LEGEND_ART_S3_SECRET_KEY"),
        ("LL_AI_PRODUCTION_ENABLED", "LL_ILLUSTRATION_ENABLED",
         "LL_IMAGE_AI_CONSENT_ENABLED"),
    ),
    ServiceContract(
        "pdf", "railway.little-legend-worker.toml",
        "python -m app.little_legend.paid_book_worker",
        ("DATABASE_URL", "BOT_TOKEN",
         "LITTLE_LEGEND_ART_S3_ENDPOINT", "LITTLE_LEGEND_ART_S3_BUCKET",
         "LITTLE_LEGEND_ART_S3_REGION", "LITTLE_LEGEND_ART_S3_ACCESS_KEY",
         "LITTLE_LEGEND_ART_S3_SECRET_KEY",
         "LITTLE_LEGEND_S3_ENDPOINT", "LITTLE_LEGEND_S3_BUCKET",
         "LITTLE_LEGEND_S3_REGION", "LITTLE_LEGEND_S3_ACCESS_KEY_ID",
         "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY"),
    ),
)


def check_service_config(service: ServiceContract, root: Path) -> list[str]:
    """Check repository config-as-code without accessing secrets."""
    path = root / service.config
    if not path.is_file():
        return [f"{service.name}: missing Railway config {service.config}"]
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    deploy = config.get("deploy", {})
    problems: list[str] = []
    if deploy.get("startCommand") != service.command:
        problems.append(f"{service.name}: unexpected startCommand")
    if deploy.get("restartPolicyType") != "ON_FAILURE":
        problems.append(f"{service.name}: restart policy must be ON_FAILURE")
    retries = deploy.get("restartPolicyMaxRetries")
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 1:
        problems.append(f"{service.name}: restart retry budget is missing")
    return problems


def check_service_environment(
    service: ServiceContract, env: Mapping[str, str],
) -> list[str]:
    """Return variable names only, never values or credential fragments."""
    problems = [
        f"{service.name}: missing {name}"
        for name in service.required if not env.get(name, "").strip()
    ]
    problems.extend(
        f"{service.name}: {name} must be true"
        for name in service.enabled if env.get(name) != "true"
    )
    for name in ("LITTLE_LEGEND_ART_S3_ENDPOINT", "LITTLE_LEGEND_S3_ENDPOINT"):
        if name in service.required and env.get(name) and not env[name].startswith("https://"):
            problems.append(f"{service.name}: {name} must use HTTPS")
    if "LL_ILLUSTRATION_PRICE_MICRO_USD" in service.required:
        price = env.get("LL_ILLUSTRATION_PRICE_MICRO_USD", "")
        if price and (not price.isdecimal() or not 0 < int(price) <= 250000):
            problems.append(f"{service.name}: invalid LL_ILLUSTRATION_PRICE_MICRO_USD")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Little Legend Railway safe preflight")
    parser.add_argument("--service", choices=[item.name for item in SERVICES])
    parser.add_argument("--check-env", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    chosen = [s for s in SERVICES if args.service is None or s.name == args.service]
    errors: list[str] = []
    for service in chosen:
        errors.extend(check_service_config(service, root))
        if args.check_env:
            errors.extend(check_service_environment(service, os.environ))
    for error in errors:
        print(f"FAIL {error}")
    if errors:
        return 1
    print("OK Little Legend Railway contracts" +
          (" and environment" if args.check_env else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
