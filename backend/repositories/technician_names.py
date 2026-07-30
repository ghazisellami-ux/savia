"""Database adapter for technician display-name lookup."""

from collections.abc import Callable
from typing import Any


class DatabaseTechnicianNameRepository:
    """Read technician names through the application's connection factory."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def find_full_name(self, username: str) -> str | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                "SELECT nom, prenom FROM techniciens WHERE username = %s",
                (username,),
            ).fetchone()
        if not row:
            return None
        last_name = row.get("nom", "").strip()
        first_name = row.get("prenom", "").strip()
        return f"{first_name} {last_name}".strip() if first_name else last_name
