import json

from repositories.technician_work import _deduct_stock_once_for_completed_technician


class _Result:
    def __init__(self, rowcount=1, row=None):
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, technician_row):
        self.technician_row = technician_row
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT statut" in query:
            return _Result(row=self.technician_row)
        return _Result()


def test_completed_technician_deducts_saved_parts_and_marks_assignment():
    conn = _Connection(
        {
            "statut": "Cloturee",
            "pieces_a_deduire": json.dumps([{"reference": "REF-42", "quantite": 3}]),
            "stock_deducted": False,
        }
    )

    _deduct_stock_once_for_completed_technician(conn, 81, 14)

    stock_updates = [query for query, _ in conn.calls if "UPDATE pieces_rechange" in query]
    marker_updates = [query for query, _ in conn.calls if "SET stock_deducted = TRUE" in query]
    assert len(stock_updates) == 1
    assert len(marker_updates) == 1


def test_completed_technician_does_not_deduct_twice():
    conn = _Connection(
        {
            "statut": "Cloturee",
            "pieces_a_deduire": json.dumps([{"reference": "REF-42", "quantite": 3}]),
            "stock_deducted": True,
        }
    )

    _deduct_stock_once_for_completed_technician(conn, 81, 14)

    assert len(conn.calls) == 1
