"""CI deployment smoke: four Railway services and credential safety."""
from pathlib import Path

import pytest

from app.little_legend.deployment_preflight import (
    SERVICES,
    check_service_config,
    check_service_environment,
    main,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.name)
def test_railway_command_and_restart_policy(service):
    assert check_service_config(service, ROOT) == []


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.name)
def test_railway_service_disabled_by_default(service):
    problems = check_service_environment(service, {})
    assert problems
    for flag in service.enabled:
        assert any(flag in problem for problem in problems)


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.name)
def test_railway_service_accepts_complete_synthetic_environment(service):
    env = {name: "synthetic-value" for name in service.required}
    env.update({name: "true" for name in service.enabled})
    for name in ("LITTLE_LEGEND_ART_S3_ENDPOINT", "LITTLE_LEGEND_S3_ENDPOINT"):
        if name in env:
            env[name] = "https://example.invalid"
    if "LL_ILLUSTRATION_PRICE_MICRO_USD" in env:
        env["LL_ILLUSTRATION_PRICE_MICRO_USD"] = "50000"
    assert check_service_environment(service, env) == []


def test_separate_service_commands_and_config_paths():
    assert len({service.command for service in SERVICES}) == 4
    assert len({service.config for service in SERVICES}) == 4
    assert {service.name for service in SERVICES} == {
        "conductor", "writer", "illustration", "pdf",
    }


def test_preflight_never_leaks_secret_values():
    service = next(s for s in SERVICES if s.name == "illustration")
    secret = "my-private-secret-12345"
    env = {name: secret for name in service.required}
    problems = check_service_environment(service, env)
    assert problems
    assert secret not in repr(problems)


def test_invalid_price_fails_closed():
    service = next(s for s in SERVICES if s.name == "conductor")
    env = {
        "DATABASE_URL": "postgresql://example.invalid/db",
        "LL_ILLUSTRATION_PRICE_MICRO_USD": "0",
        "LL_CONDUCTOR_ENABLED": "true",
    }
    assert any("invalid" in issue for issue in check_service_environment(service, env))
    env["LL_ILLUSTRATION_PRICE_MICRO_USD"] = "not-an-int"
    assert any("invalid" in issue for issue in check_service_environment(service, env))


def test_cli_contract_smoke(capsys):
    assert main([]) == 0
    assert "OK Little Legend" in capsys.readouterr().out
