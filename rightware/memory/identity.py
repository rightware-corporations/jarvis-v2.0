"""Owner identity contract for personal memory.

A memory owner is a STABLE, host-declared identity — never the temporary B6 session id, a cookie, a client header or
anything the model or a page says. Today there is no durable, verified user identity in the product (B6 proves
possession of a one-time link, not who the person is). Therefore:

* ``StaticOwner``: one owner per JARVIS process, declared by the operator at start-up (single-person deployment,
  e.g. Issa's own computer). Every session of that process acts for that owner.
* ``lab:<name>`` owners: synthetic identities for tests and acceptance runs.

PENDING (documented, not done here): binding an authenticated B6 session to a verified owner (e.g. per-person
one-time links issued for a named owner, or OS-account identity on a local install). That touches ``auth.py``/B6 and
is coordinated separately; until then a shared server must NOT mix people under one owner.
"""
from __future__ import annotations

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
