"""SAVIA FastAPI composition root.

The application object remains available as `main:app`. Route implementations
live in layer-specific controller modules and are imported in their historical
registration order to preserve FastAPI matching behavior.
"""

from api.runtime import *
from services.scheduled_jobs import *
from api.lifecycle import *
from api.security import *

from controllers.auth_dashboard import *
from controllers.predictions import *
from controllers.equipment import *
from controllers.interventions import *
from controllers.requests import *
from controllers.parts import *
from controllers.contracts import *
from controllers.planning import *
from controllers.knowledge import *
from controllers.ai import *
from controllers.ai_governance import *
from controllers.admin import *
from controllers.clients_dashboard import *
from controllers.storage import *
from controllers.observability import *
from controllers.report_helpers import *
from controllers.pdf_reports import *
from controllers.pdf_intervention import *
from controllers.pdf_attestation import *
from controllers.pdf_contract import *
from controllers.finance import *
from controllers.billing import *
from controllers.public_markets import *

import controllers.ai as _ai_controller
import controllers.finance as _finance_controller
import controllers.report_helpers as _report_helpers

_ai_controller.finances_tco = _finance_controller.finances_tco
_ai_controller.SaviaPDF = _report_helpers.SaviaPDF
_ai_controller._fmt_number = _report_helpers._fmt_number
_ai_controller._sanitize = _report_helpers._sanitize


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
