"""WORK-07 Milestone A1: trusted-preset input validation (LAB ONLY).

This is a small executable spec, NOT a product authorization entrypoint.
The only acceptable origin is a code-owned registry supplied by trusted code.
Neither model text nor arbitrary dicts can be promoted to a trusted preset.
No effects on RIGHTWARE policy, permissions, agent completion or Qwen.
"""
from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlsplit

MAX_OBJECTIVES = 8
MAX_HOSTS = 4


@dataclass(frozen=True)
class Objective:
    oid: str
    action: str
    url: str
    mandatory: bool = True


@dataclass(frozen=True)
class Preset:
    preset_id: str
    version: str
    objectives: tuple[Objective, ...]
    hosts: tuple[str, ...]
    provenance: str = "approved_preset"
    max_continuations: int = 1


def validate_preset(preset: Preset, *, allowed_sites: tuple[str, ...], browse_allowed: bool) -> Preset:
    if type(preset) is not Preset:
        raise ValueError("preset must be an internally constructed Preset")
    if not browse_allowed:
        raise ValueError("browse capability not enabled")
    if preset.version != "A1" or preset.provenance != "approved_preset":
        raise ValueError("unsupported schema or provenance")
    if not isinstance(preset.preset_id, str) or not preset.preset_id or len(preset.preset_id) > 80:
        raise ValueError("invalid preset id")
    if not isinstance(preset.objectives, tuple) or not (1 <= len(preset.objectives) <= MAX_OBJECTIVES):
        raise ValueError("objective count")
    if not isinstance(preset.hosts, tuple) or not (1 <= len(preset.hosts) <= MAX_HOSTS):
        raise ValueError("host count")
    if preset.max_continuations not in (0, 1):
        raise ValueError("unsafe continuation limit")
    site_set = set()
    for item in allowed_sites:
        if not isinstance(item, str) or not item or item != item.lower().rstrip("."):
            raise ValueError("invalid allowed site")
        site_set.add(item)
    if len(set(preset.hosts)) != len(preset.hosts):
        raise ValueError("duplicate hosts")
    for host in preset.hosts:
        if not isinstance(host, str) or not host or host != host.lower().rstrip(".") or host not in site_set:
            raise ValueError("host exceeds session allowlist")
    ids = set()
    mandatory = 0
    for o in preset.objectives:
        if type(o) is not Objective or not isinstance(o.oid, str) or not o.oid or len(o.oid) > 80:
            raise ValueError("invalid objective")
        if o.oid in ids:
            raise ValueError("duplicate objective")
        ids.add(o.oid)
        if type(o.mandatory) is not bool or not o.mandatory:
            raise ValueError("A1 supports mandatory objectives only")
        mandatory += 1
        if o.action not in ("read_page", "open_original"):
            raise ValueError("unsupported action")
        if not isinstance(o.url, str) or len(o.url) > 2048 or any(ord(c) < 33 for c in o.url):
            raise ValueError("invalid URL")
        u = urlsplit(o.url)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
            raise ValueError("URL must be canonical public HTTPS")
        if u.hostname not in preset.hosts or (u.port not in (None, 443)):
            raise ValueError("host/port is not approved")
        if not u.path.startswith("/") or u.netloc.lower() != u.netloc:
            raise ValueError("noncanonical URL")
        if u.query:
            raise ValueError("A1 excludes query strings in expected source URLs")
    if not mandatory:
        raise ValueError("no mandatory objectives")
    return preset


class PresetRegistry:
    """Only code-owned presets are eligible; the model cannot register a dict."""
    def __init__(self, entries: tuple[Preset, ...]):
        if not isinstance(entries, tuple) or any(type(x) is not Preset for x in entries):
            raise ValueError("invalid registry source")
        by_id = {p.preset_id: p for p in entries}
        if len(by_id) != len(entries):
            raise ValueError("duplicate registry ids")
        self._by_id = MappingProxyType(by_id)

    def select(self, preset_id: str, *, allowed_sites: tuple[str, ...], browse_allowed: bool) -> Preset:
        if not isinstance(preset_id, str) or preset_id not in self._by_id:
            raise ValueError("unknown preset: no model-supplied contracts")
        return validate_preset(self._by_id[preset_id], allowed_sites=allowed_sites,
                               browse_allowed=browse_allowed)


SYNTHETIC_ARCHIVE_PRESET = Preset(
    preset_id="test-archive-two-originals",
    version="A1",
    hosts=("archive.fixture.example",),
    objectives=(
        Objective("AX101", "open_original", "https://archive.fixture.example/docs/ax-101.html"),
        Objective("AX202", "open_original", "https://archive.fixture.example/docs/ax-202.html"),
    ),
)
TEST_REGISTRY = PresetRegistry((SYNTHETIC_ARCHIVE_PRESET,))
