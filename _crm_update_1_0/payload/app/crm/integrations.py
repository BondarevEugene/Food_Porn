"""Read-only advertising adapters. Credentials never enter report responses."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

PROVIDERS = {"meta", "google_ads"}
SECRET_FIELDS = {
    "meta": {"access_token"},
    "google_ads": {"client_secret", "refresh_token", "developer_token"},
}
CONFIG_FIELDS = {
    "meta": {"ad_account_id", "pixel_id", "api_version"},
    "google_ads": {"customer_id", "login_customer_id", "client_id", "api_version"},
}


class ProviderError(ValueError):
    pass


def validate_configuration(provider: str, config: dict, credentials: dict) -> tuple[dict, dict]:
    if (
        provider not in PROVIDERS
        or set(config) - CONFIG_FIELDS[provider]
        or set(credentials) - SECRET_FIELDS[provider]
    ):
        raise ValueError("Неизвестные поля интеграции")
    if any(
        not isinstance(value, str) or len(value) > 8192
        for value in [*config.values(), *credentials.values()]
    ):
        raise ValueError("Поля должны содержать строки")
    config = {key: value.strip() for key, value in config.items()}
    credentials = {key: value.strip() for key, value in credentials.items() if value.strip()}
    if provider == "meta":
        config.setdefault("api_version", "v24.0")
        account = config.get("ad_account_id", "").removeprefix("act_")
        if not re.fullmatch(r"[0-9]{4,30}", account):
            raise ValueError("Укажите числовой Ad Account ID Meta")
        config["ad_account_id"] = account
        if not re.fullmatch(r"v[0-9]{1,2}\.0", config["api_version"]):
            raise ValueError("Версия Meta должна иметь формат v24.0")
        if config.get("pixel_id") and not config["pixel_id"].isdigit():
            raise ValueError("Pixel ID должен быть числом")
    else:
        config.setdefault("api_version", "v25")
        for key in ("customer_id", "login_customer_id"):
            value = config.get(key, "").replace("-", "")
            if (key == "customer_id" or value) and not re.fullmatch(r"[0-9]{10}", value):
                raise ValueError(f"{key}: нужны 10 цифр")
            config[key] = value
        if not re.fullmatch(r"v[0-9]{1,2}", config["api_version"]):
            raise ValueError("Версия Google Ads должна иметь формат v25")
        if not config.get("client_id"):
            raise ValueError("Укажите Google OAuth Client ID")
    return config, credentials


def _numeric(value) -> Decimal:
    result = Decimal(str(value or 0))
    if not result.is_finite() or result < 0:
        raise ProviderError("Рекламный API вернул некорректные показатели")
    return result


async def _response(response: httpx.Response, provider: str):
    if not response.is_success:
        raise ProviderError(
            f"{provider}: HTTP {response.status_code}. Проверьте доступ к аккаунту, API-версию и токен."
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider}: получен ответ не в JSON") from exc


async def fetch_meta(client, config: dict, credentials: dict, days: int) -> dict:
    import json

    token = credentials.get("access_token")
    if not token:
        raise ProviderError("Meta Access Token не указан")
    base = f"https://graph.facebook.com/{config['api_version']}/act_{config['ad_account_id']}"
    headers = {"Authorization": f"Bearer {token}"}
    account = await _response(
        await client.get(base, headers=headers, params={"fields": "id,name,currency"}), "Meta"
    )
    until = datetime.now(UTC).date()
    since = until - timedelta(days=days - 1)
    params = {
        "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions",
        "level": "campaign",
        "limit": "100",
        "time_range": json.dumps({"since": str(since), "until": str(until)}),
    }
    campaigns = []
    truncated = False
    for _ in range(50):
        report = await _response(
            await client.get(f"{base}/insights", headers=headers, params=params), "Meta"
        )
        for row in report.get("data", []):
            campaigns.append(
                {
                    "id": str(row.get("campaign_id", "")),
                    "name": row.get("campaign_name", ""),
                    "spend": str(_numeric(row.get("spend"))),
                    "impressions": int(_numeric(row.get("impressions"))),
                    "clicks": int(_numeric(row.get("clicks"))),
                    "currency": account.get("currency", ""),
                    "conversions": str(
                        next(
                            (
                                _numeric(action.get("value"))
                                for action in row.get("actions", [])
                                if action.get("action_type") == "omni_purchase"
                            ),
                            next(
                                (
                                    _numeric(action.get("value"))
                                    for action in row.get("actions", [])
                                    if action.get("action_type")
                                    == "offsite_conversion.fb_pixel_purchase"
                                ),
                                Decimal(0),
                            ),
                        )
                    ),
                }
            )
        # Do not follow the API-supplied URL: it can contain credentials.
        paging = report.get("paging", {})
        after = paging.get("cursors", {}).get("after")
        if not paging.get("next") or not after:
            break
        params["after"] = after
    else:
        truncated = True
    return {
        "account": account.get("name", ""),
        "currency": account.get("currency", ""),
        "campaigns": campaigns,
        "since": str(since),
        "until": str(until),
        "truncated": truncated,
    }


async def fetch_google(client, config: dict, credentials: dict, days: int) -> dict:
    if not credentials.get("client_secret") or not credentials.get("refresh_token"):
        raise ProviderError("Укажите OAuth Client Secret и Refresh Token Google")
    oauth = await _response(
        await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "client_id": config["client_id"],
                "client_secret": credentials["client_secret"],
                "refresh_token": credentials["refresh_token"],
            },
        ),
        "Google OAuth",
    )
    access_token = oauth.get("access_token")
    if not access_token:
        raise ProviderError("Google OAuth не вернул Access Token")
    headers = {"Authorization": f"Bearer {access_token}"}
    if credentials.get("developer_token"):
        headers["developer-token"] = credentials["developer_token"]
    if config.get("login_customer_id"):
        headers["login-customer-id"] = config["login_customer_id"]
    until = datetime.now(UTC).date()
    since = until - timedelta(days=days - 1)
    url = f"https://googleads.googleapis.com/{config['api_version']}/customers/{config['customer_id']}/googleAds:searchStream"
    info = await _response(
        await client.post(
            url,
            headers=headers,
            json={
                "query": "SELECT customer.descriptive_name, customer.currency_code FROM customer LIMIT 1"
            },
        ),
        "Google Ads",
    )
    customer = next(
        (row.get("customer", {}) for batch in info for row in batch.get("results", [])), {}
    )
    query = (
        "SELECT campaign.id, campaign.name, campaign.status, metrics.impressions, "
        "metrics.clicks, metrics.cost_micros, metrics.conversions FROM campaign "
        f"WHERE segments.date BETWEEN '{since}' AND '{until}' AND campaign.status != 'REMOVED'"
    )
    result = await _response(
        await client.post(url, headers=headers, json={"query": query}), "Google Ads"
    )
    campaigns = []
    for batch in result:
        for row in batch.get("results", []):
            campaign, metrics = row.get("campaign", {}), row.get("metrics", {})
            campaigns.append(
                {
                    "id": str(campaign.get("id", "")),
                    "name": campaign.get("name", ""),
                    "status": campaign.get("status", ""),
                    "currency": customer.get("currencyCode", ""),
                    "spend": str(_numeric(metrics.get("costMicros")) / Decimal(1000000)),
                    "impressions": int(_numeric(metrics.get("impressions"))),
                    "clicks": int(_numeric(metrics.get("clicks"))),
                    "conversions": str(_numeric(metrics.get("conversions"))),
                }
            )
    return {
        "account": customer.get("descriptiveName", ""),
        "currency": customer.get("currencyCode", ""),
        "campaigns": campaigns,
        "since": str(since),
        "until": str(until),
        "truncated": False,
    }


async def fetch_report(provider: str, config: dict, credentials: dict, days: int = 30) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            if provider == "meta":
                return await fetch_meta(client, config, credentials, days)
            return await fetch_google(client, config, credentials, days)
    except httpx.HTTPError as exc:
        raise ProviderError("Рекламный API недоступен. Повторите синхронизацию позже.") from exc
