"""Backward-compatible database API.

Implementation is split by persistence responsibility. Existing callers can keep
importing from :mod:`db_engine` without changing names or signatures.
"""

import json
from datetime import timedelta

from database.core import *
from database.core import (
    _auto_migrate_vps_schema,
    _extract_piece_refs_from_text,
    _fill_missing_cout_pieces,
    _pieces_cost_from_text,
    _trigger_backup,
)
from repositories.assets import *
from repositories.audit import *
from repositories.contracts import *
from repositories.equipment_status import *
from repositories.interventions import *
from repositories.knowledge import *
from repositories.parts import *
from repositories.parts_prediction import *
from repositories.requests import *
from repositories.technician_work import *
