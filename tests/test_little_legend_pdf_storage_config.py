"""Private storage configuration must fail closed without credentials."""
from unittest.mock import patch

import pytest

from app.little_legend.pdf_storage_config import configured_private_pdf_store


def test_missing_private_storage_configuration_is_rejected() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="not configured"):
            configured_private_pdf_store()


def test_http_private_storage_endpoint_is_rejected() -> None:
    values = {
        "LITTLE_LEGEND_S3_ENDPOINT_URL": "http://localhost:9000",
        "LITTLE_LEGEND_S3_BUCKET": "books",
        "LITTLE_LEGEND_S3_REGION": "auto",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID": "access",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY": "secret",
    }
    with patch.dict("os.environ", values, clear=True):
        with pytest.raises(ValueError, match="not configured"):
            configured_private_pdf_store()


def test_https_private_storage_configuration_builds_adapter() -> None:
    values = {
        "LITTLE_LEGEND_S3_ENDPOINT_URL": "https://private.example.test",
        "LITTLE_LEGEND_S3_BUCKET": "books",
        "LITTLE_LEGEND_S3_REGION": "auto",
        "LITTLE_LEGEND_S3_ACCESS_KEY_ID": "access",
        "LITTLE_LEGEND_S3_SECRET_ACCESS_KEY": "secret",
    }
    with (
        patch.dict("os.environ", values, clear=True),
        patch(
            "app.little_legend.pdf_storage_config.S3PrivatePDFStore",
        ) as adapter,
    ):
        configured_private_pdf_store()
    adapter.assert_called_once()
    settings = adapter.call_args.args[0]
    assert settings.endpoint_url == values["LITTLE_LEGEND_S3_ENDPOINT_URL"]
    assert settings.bucket == "books"
