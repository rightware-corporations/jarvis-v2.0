"""Owner identity contract for personal memory.

A memory owner is a STABLE, host-declared identity — never the temporary B6 session id, a cookie, a client header or
anything the model or a page says. Today there is no durable, verified user identity in the product (B6 proves
possession of a one-time link, not who the person is). Therefore:

* ``StaticOwner``: one owner per JARVIS process, declared by the operator at start-up (single-person deployment,
  e.g. Issa's own computer). Every session of that process acts for that owner.
* ``lab:<name>`` owners: synthetic identities for tests and acceptance runs.

INT01 (done): ``SessionOwner`` — each B6 one-time link is issued by the server for a DECLARED owner label (e.g.
operador → lab:operador, issa → lab:issa); the authenticated session inherits that owner and the bridge sets it for
the request (``CURRENT_OWNER``). The browser never chooses it. B6 still proves possession of a link, not a person:
the operator decides to whom each link is delivered.
"""
from __future__ import annotations

import contextvars
import dataclasses
import re

OWNER_RE = re.compile(r"^(lab|local|user):[a-z0-9][a-z0-9._-]{0,62}$")


@dataclasses.dataclass(frozen=True)
class Owner:
    owner_id: str            # e.g. "lab:alfa", "local:issa"
    verified_by: str         # how the host knows: "operator-config" | "lab-synthetic"

    def __post_init__(self):
        if not OWNER_RE.match(self.owner_id):
            raise ValueError("identificador de dono inválido (formato lab:|local:|user:<nome>)")


class StaticOwner:
    """The owner of every request of this process (host configuration)."""

    def __init__(self, owner_id: str, verified_by: str = "operator-config"):
        self.owner = Owner(owner_id, verified_by)

    def __call__(self) -> Owner:
        return self.owner


# INT01: owner of the CURRENT request, set by the GUI bridge from the authenticated session (never from the
# browser). Propagated into worker threads with contextvars.copy_context().
CURRENT_OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar("rightware_owner", default=None)


class SessionOwner:
    """Owner from the authenticated session of this request (B6 link issued for a server-declared owner).
    Without a session owner: the optional ``fallback`` (single-person local deployment) or None (no memory and no
    documents for that request)."""

    def __init__(self, fallback=None):
        self.fallback = fallback

    def __call__(self) -> Owner | None:
        oid = CURRENT_OWNER.get()
        if oid:
            return Owner(oid, "b6-session-link")
        return self.fallback() if self.fallback is not None else None
