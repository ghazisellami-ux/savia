"""Technician identity matching and display-name policy."""

import logging
import re
from typing import Protocol


class TechnicianNameLookup(Protocol):
    def find_full_name(self, username: str) -> str | None:
        """Return a technician's full name, or None when no row exists."""


class TechnicianIdentityService:
    """Resolve technician names and compare assignments without persistence details."""

    def __init__(
        self,
        repository: TechnicianNameLookup,
        logger: logging.Logger | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger or logging.getLogger("savia-api")

    def resolve_full_name(self, username: str) -> str:
        if not username:
            return ""
        try:
            full_name = self._repository.find_full_name(username)
            return username if full_name is None else full_name
        except Exception as exc:
            self._logger.debug(f"Failed to get technician name for {username}: {exc}")
            return username

    @staticmethod
    def extract_words(text: str) -> list[str]:
        cleaned = re.sub(r"[,;/\-_\.\(\)\[\]]+", " ", text.lower())
        return [word for word in cleaned.split() if word.strip()]

    def name_matches(self, user_name: str, technician_field: str) -> bool:
        if not user_name or not technician_field:
            self._logger.warning(
                f"[_tech_name_matches] Empty inputs: user_name='{user_name}', technicien_field='{technician_field}'"
            )
            return False

        user_words = self.extract_words(user_name)
        technician_words = self.extract_words(technician_field)
        self._logger.info(
            f"[_tech_name_matches] Comparing: user='{user_name}' (words={user_words}) "
            f"vs tech='{technician_field}' (words={technician_words})"
        )
        if not user_words:
            self._logger.warning(f"[_tech_name_matches] No user words extracted from '{user_name}'")
            return False
        if not technician_words:
            self._logger.warning(f"[_tech_name_matches] No tech words extracted from '{technician_field}'")
            return False

        result = all(word in technician_words for word in user_words)
        self._logger.info(
            f"[_tech_name_matches] Result: {result} "
            f"(all user_words in tech_words: {[word in technician_words for word in user_words]})"
        )
        return result

    def name_or_username_matches(self, user_name_or_username: str, technician_field: str) -> bool:
        if not user_name_or_username or not technician_field:
            return False
        if user_name_or_username.lower() == technician_field.lower():
            return True
        return self.name_matches(user_name_or_username, technician_field)
