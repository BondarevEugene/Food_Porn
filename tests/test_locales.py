"""
==========================================================
FOOD_PORN

Module: Localization Tests
Layer: Test

Responsibilities:
    - Verify required strings exist in every language
    - Verify localized templates format correctly
==========================================================
"""

from app.database.models import Language
from app.locales.messages import t


def test_all_languages_have_core_strings() -> None:
    for language in Language:
        assert t("main_section", language)
        assert t("salad_section", language)
        assert t("drink_section", language)
        assert t("retry_generation", language)
        assert t("quota_exhausted", language)
        assert "{name}" not in t("welcome_back", language, name="Anna")
