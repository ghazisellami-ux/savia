from database.migrations.runner import _migration_023_contract_multiple_attachments


class _RecordingConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(" ".join(statement.split()))


def test_contract_attachment_migration_creates_and_backfills_attachment_table():
    connection = _RecordingConnection()

    _migration_023_contract_multiple_attachments(connection)

    statements = "\n".join(connection.statements)
    assert "CREATE TABLE IF NOT EXISTS contrat_fichiers" in statements
    assert "REFERENCES contrats(id) ON DELETE CASCADE" in statements
    assert "idx_contrat_fichiers_content" in statements
    assert "INSERT INTO contrat_fichiers" in statements
    assert "ON CONFLICT (storage_key) DO NOTHING" in statements
