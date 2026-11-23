"""Historical alias (JRV-P3A). The implementation now lives in ``rightware.gateway.synthetic.score_semantic``; this name is kept so the
TE-P2A..C tests and scripts import the SAME module object (no second implementation)."""
import sys

from rightware.gateway.synthetic import score_semantic as _impl

if __name__ == "__main__":
    import json
    print(json.dumps(_impl.check(json.load(open(sys.argv[1], encoding="utf-8"))), ensure_ascii=False, indent=2))
else:
    sys.modules[__name__] = _impl
