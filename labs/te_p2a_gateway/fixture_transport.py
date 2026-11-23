"""Historical alias (JRV-P3A). The implementation now lives in ``rightware.gateway.synthetic.fixture_transport``; this name is kept so the
TE-P2A..C tests and scripts import the SAME module object (no second implementation)."""
import sys

from rightware.gateway.synthetic import fixture_transport as _impl

sys.modules[__name__] = _impl
