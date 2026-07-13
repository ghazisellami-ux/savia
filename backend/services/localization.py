"""Language selection and user-facing text translation services."""

from collections.abc import Callable, Mapping
from contextvars import ContextVar
import json
import logging
import unicodedata
from typing import Any


ConfigReader = Callable[[str, str], Any]


class LocalizationService:
    """Translate user-facing values while keeping request-local language state."""

    def __init__(
        self,
        english_translations: Mapping[str, str],
        config_reader: ConfigReader,
        logger: logging.Logger | None = None,
    ) -> None:
        self._english_translations = dict(english_translations)
        self._config_reader = config_reader
        self._logger = logger or logging.getLogger("savia-api")
        self.language_context: ContextVar[str] = ContextVar("savia_lang", default="fr")

    @staticmethod
    def repair_mojibake(text: str) -> str:
        current = str(text)
        for _ in range(2):
            if not any(marker in current for marker in ("Ã", "Â", "â")):
                break
            try:
                repaired = current.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
            except Exception:
                break
            if repaired == current:
                break
            current = repaired
        return current

    @staticmethod
    def strip_diacritics(text: str) -> str:
        return "".join(
            char
            for char in unicodedata.normalize("NFD", str(text))
            if unicodedata.category(char) != "Mn"
        )

    def translation_variants(self, text: str) -> list[str]:
        original = str(text)
        repaired = self.repair_mojibake(original)
        variants = [
            original,
            repaired,
            self.strip_diacritics(original),
            self.strip_diacritics(repaired),
        ]
        return list(dict.fromkeys(variant for variant in variants if variant))

    def expanded_english_translations(self) -> dict[str, str]:
        expanded: dict[str, str] = {}
        for source, target in self._english_translations.items():
            for variant in self.translation_variants(source):
                expanded[variant] = target
        return expanded

    @staticmethod
    def normalize_language(lang: str | None = None) -> str:
        return "en" if str(lang or "").lower().startswith("en") else "fr"

    def get_app_language(
        self,
        header_lang: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> str:
        requested = None
        if isinstance(body, dict):
            requested = body.get("lang") or body.get("language") or body.get("locale")
        try:
            configured = self._config_reader("langue", "fr") or "fr"
        except Exception:
            configured = "fr"
        return self.normalize_language(requested or header_lang or configured)

    def ai_language_instruction(self, lang: str) -> str:
        if self.normalize_language(lang) == "en":
            return (
                "IMPORTANT LANGUAGE RULE: Write every user-facing value in English only. "
                "Keep the JSON keys exactly as specified. If examples or source data below are in French, "
                "translate their labels and generated text to English."
            )
        return (
            "IMPORTANT: Rédige toutes les valeurs destinées à l'utilisateur en français. "
            "Garde exactement les clés JSON demandées."
        )

    def translate_text(self, text: str, lang: str | None = None) -> str:
        if self.normalize_language(lang or self.language_context.get()) != "en" or not text:
            return text
        translated_text = self.repair_mojibake(str(text))
        translations = self.expanded_english_translations()
        for candidate in self.translation_variants(translated_text):
            if candidate in translations:
                return translations[candidate]
        for source, target in sorted(translations.items(), key=lambda item: len(item[0]), reverse=True):
            translated_text = translated_text.replace(source, target)
        return translated_text

    def fallback_translate_payload(self, payload: Any, lang: str) -> Any:
        if self.normalize_language(lang) != "en":
            return payload
        if isinstance(payload, dict):
            return {key: self.fallback_translate_payload(value, lang) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self.fallback_translate_payload(value, lang) for value in payload]
        if isinstance(payload, str):
            return self.translate_text(payload, lang)
        return payload

    def force_ai_payload_language(
        self,
        payload: Any,
        lang: str,
        call_ia: Callable[..., Any] | None = None,
        clean_json: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Translate AI user-facing values to English while preserving JSON keys."""
        if self.normalize_language(lang) != "en" or payload is None:
            return payload
        fallback = self.fallback_translate_payload(payload, lang)
        if not call_ia or not clean_json:
            return fallback
        try:
            wrapped = {"value": payload} if isinstance(payload, str) else payload
            prompt = (
                "Translate every user-facing string value in this JSON to natural professional English. "
                "Preserve all JSON keys exactly, preserve numbers/booleans/nulls, preserve arrays and object structure. "
                "Return only valid JSON, with no markdown.\n\n"
                f"JSON:\n{json.dumps(wrapped, ensure_ascii=False, default=str)}"
            )
            raw = call_ia(prompt, timeout=60, is_json=True)
            translated = clean_json(raw) if raw else None
            if isinstance(payload, str) and isinstance(translated, dict) and isinstance(translated.get("value"), str):
                return translated["value"]
            if isinstance(payload, dict) and isinstance(translated, dict):
                return translated
            if isinstance(payload, list) and isinstance(translated, list):
                return translated
        except Exception as exc:
            self._logger.debug(f"AI language post-translation skipped: {exc}")
        return fallback
