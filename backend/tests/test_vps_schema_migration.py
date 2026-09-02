from database.core import _auto_migrate_vps_schema


class _MigrationCursor:
    def __init__(self, columns):
        self.columns = columns
        self.queries = []
        self.rowcount = 0
        self._one = None
        self._many = []

    def execute(self, query):
        normalized = " ".join(query.split())
        self.queries.append(normalized)
        self._one = None
        self._many = []

        if "FROM information_schema.tables" in normalized:
            self._one = {"table_exists": True}
        elif "FROM information_schema.columns" in normalized:
            self._many = [{"column_name": column} for column in self.columns]
        elif normalized.startswith("UPDATE contrats_equipements"):
            self.rowcount = 1
        elif "FROM information_schema.table_constraints" in normalized:
            self._one = None

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _MigrationConnection:
    def __init__(self, columns):
        self.migration_cursor = _MigrationCursor(columns)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.migration_cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_legacy_vps_schema_is_migrated_with_mapping_cursor_rows():
    connection = _MigrationConnection(["id", "contrat_id", "equipement_nom", "created_at"])

    _auto_migrate_vps_schema(connection)

    executed = "\n".join(connection.migration_cursor.queries)
    assert "ADD COLUMN equipement_id INTEGER" in executed
    assert "UPDATE contrats_equipements ce SET equipement_id = e.id" in executed
    assert "ADD CONSTRAINT contrats_equipements_equipement_id_fkey" in executed
    assert "DROP COLUMN equipement_nom" in executed
    assert connection.commits == 4
    assert connection.rollbacks == 0


def test_standard_vps_schema_does_not_run_migration_statements():
    connection = _MigrationConnection(["id", "contrat_id", "equipement_id", "created_at"])

    _auto_migrate_vps_schema(connection)

    executed = "\n".join(connection.migration_cursor.queries)
    assert "ALTER TABLE contrats_equipements" not in executed
    assert "UPDATE contrats_equipements" not in executed
    assert connection.commits == 0
    assert connection.rollbacks == 0
