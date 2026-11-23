"""Historical alias (JRV-P3A). The implementation now lives in ``rightware.gateway.report_contract``; this name is kept so the
TE-P2A..C tests and scripts import the SAME module object (no second implementation)."""
import sys

from rightware.gateway import report_contract as _impl

sys.modules[__name__] = _impl
