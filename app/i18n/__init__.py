import json
import os

_translations: dict[str, dict] = {}
_current_lang: str = "ja"
_i18n_dir = os.path.dirname(__file__)


def load_language(lang: str) -> dict:
    """Load a language file and cache it."""
    if lang not in _translations:
        path = os.path.join(_i18n_dir, f"{lang}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _translations[lang] = json.load(f)
        else:
            _translations[lang] = {}
    return _translations[lang]


def set_language(lang: str) -> None:
    global _current_lang
    _current_lang = lang
    load_language(lang)


def t(key: str, **kwargs) -> str:
    """Translate a key using the current language.

    Supports nested keys with dot notation: t("stats.total_qsos")
    Supports format placeholders: t("distance_km", km=123)
    """
    data = load_language(_current_lang)
    parts = key.split(".")
    value = data
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return key  # Return key itself as fallback
    if isinstance(value, str) and kwargs:
        return value.format(**kwargs)
    return value if isinstance(value, str) else key


def get_all_translations(lang: str | None = None) -> dict:
    """Get all translations for a language (for sending to frontend)."""
    return load_language(lang or _current_lang)


def get_current_language() -> str:
    return _current_lang
