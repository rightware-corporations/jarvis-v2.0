"""WEB-01 W1: read-only research toolkit with source receipts, and the RIGHTWARE research verifier.

Tools (the only operations; both are GETs through the ``EgressGuard``):
* ``web_search_public(query)`` — the policy's search endpoint (fixture: ``pesquisa.fixture.example``);
* ``web_open_public(url)`` — one page.

Every attempt, allowed or refused, gets a receipt::

    {seq, tool, status: OK|HTTP_ERROR|REFUSED|ERROR, request, final_url, http_status, content_type, fetched_at,
     sha256, bytes, truncated, refusal, prev, hash}

``hash`` = SHA-256 of the canonical JSON of the receipt without ``hash``; ``prev`` = the previous receipt's hash
(chain). The exact response bytes are kept by the HOST (never by the model) so the verifier can re-hash them.

The verifier decides each objective of a host-defined mission spec ONLY from receipts + kept bytes:
an objective is VERIFIED when a ``web_open_public`` receipt with status OK, whose final host is one of the
objective's designated sources, has bytes that re-hash to the receipt and whose visible text matches the
objective's pattern. Pages from other hosts (e.g. a forum) can be read but never support a claim.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from rightware.agent import web as W
from rightware.web01.egress import EgressGuard, utc_now

MISSION_VERSION = "web01.mission.v1"
DEFAULT_MISSION = Path(__file__).resolve().parents[2] / "configs" / "web01" / "missions" / "ficha-mocambique.json"
GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def receipt_hash(r: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in r.items() if k != "hash"}).encode("utf-8")).hexdigest()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def links(page: W.Page) -> list[str]:
    p = _Links()
    p.feed(page.markup or "")
    out = []
    for h in p.hrefs:
        u = urljoin(page.final_url, h)
        if urlsplit(u).scheme in ("http", "https") and u not in out:
            out.append(u)
    return out


class ResearchToolkit:
    def __init__(self, guard: EgressGuard, search_url, extract=None):
        """``search_url``: query → URL (or a provider with ``search_url``/``results``); ``extract``: page → URLs."""
        if hasattr(search_url, "search_url"):
            search_url, extract = search_url.search_url, search_url.results
        self.guard, self.search_url, self.extract = guard, search_url, extract or links
        self.receipts: list[dict] = []
        self.kept: dict[int, bytes] = {}          # host-side evidence: exact bytes per receipt

    def _receipt(self, tool: str, request: str, page: W.Page | None, refusal: str | None) -> dict:
        status = "ERROR" if refusal and refusal.startswith("erro de transporte") else "REFUSED"
        r = {"seq": len(self.receipts) + 1, "tool": tool, "request": W.redact_url(request)[:500],
             "fetched_at": utc_now(), "status": status, "final_url": None, "http_status": None,
             "content_type": None, "sha256": None, "bytes": 0, "truncated": False, "refusal": refusal,
             "prev": self.receipts[-1]["hash"] if self.receipts else GENESIS}
        if page is not None:
            r.update(status="OK" if 200 <= page.status < 300 else "HTTP_ERROR",
                     final_url=W.redact_url(page.final_url)[:500], http_status=page.status,
                     content_type=page.content_type, sha256=page.sha256, bytes=len(page.raw), truncated=page.truncated)
            self.kept[r["seq"]] = page.raw
        r["hash"] = receipt_hash(r)
        self.receipts.append(r)
        return r

    def _get(self, tool: str, url: str) -> tuple[dict, W.Page | None]:
        try:
            page = self.guard.fetch(url)
        except W.WebRefused as exc:
            return self._receipt(tool, url, None, str(exc)[:200]), None
        except Exception as exc:                 # transport error/abort: receipted as ERROR, never a crash
            return self._receipt(tool, url, None, f"erro de transporte: {type(exc).__name__}"), None
        return self._receipt(tool, url, page, None), page

    def web_search_public(self, query: str) -> tuple[dict, list[str]]:
        query = " ".join(str(query).split())[:200]
        r, page = self._get("web_search_public", self.search_url(query))
        return r, (self.extract(page) if page is not None and r["status"] == "OK" else [])

    def web_open_public(self, url: str) -> tuple[dict, W.Page | None]:
        return self._get("web_open_public", url)


@dataclasses.dataclass(frozen=True)
class Objective:
    id: str
    claim: str
    query: str
    pattern: re.Pattern
    sources: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class MissionSpec:
    id: str
    question: str
    max_open: int
    objectives: tuple[Objective, ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_MISSION) -> "MissionSpec":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if d.get("version") != MISSION_VERSION or set(d) != {"version", "id", "question",
                                                             "max_results_opened_per_search", "objectives"}:
            raise ValueError("especificação de missão inválida")
        objs = []
        for o in d["objectives"]:
            if set(o) != {"id", "claim", "query", "pattern", "sources"} or not o["sources"]:
                raise ValueError("objectivo inválido")
            objs.append(Objective(o["id"], o["claim"], o["query"], re.compile(o["pattern"]), tuple(o["sources"])))
        n = d["max_results_opened_per_search"]
        if not (isinstance(n, int) and 1 <= n <= 5) or not objs or len({o.id for o in objs}) != len(objs):
            raise ValueError("especificação de missão inválida")
        return cls(d["id"], d["question"], n, tuple(objs))


def page_text(raw: bytes) -> str:
    return W.html_to_text(raw.decode("utf-8", errors="replace"))


def verify(receipts: list[dict], kept: dict[int, bytes], spec: MissionSpec, allowed_host) -> dict:
    """Pure function of receipts + kept bytes + the host's spec/policy. Never reads model text."""
    problems = []
    prev = GENESIS
    for i, r in enumerate(receipts, 1):
        if r.get("seq") != i or r.get("prev") != prev or receipt_hash(r) != r.get("hash"):
            problems.append(f"cadeia de recibos inválida em #{i}")
            break
        prev = r["hash"]
        if r["status"] in ("OK", "HTTP_ERROR"):
            raw = kept.get(r["seq"])
            if raw is None or hashlib.sha256(raw).hexdigest() != r["sha256"] or len(raw) != r["bytes"]:
                problems.append(f"bytes do recibo #{r['seq']} não correspondem ao hash")
            host = (urlsplit(r["final_url"] or "").hostname or "")
            if not allowed_host(host):
                problems.append(f"recibo #{r['seq']} de servidor fora da allowlist")
    objectives, support = [], {}
    for o in spec.objectives:
        hit = None
        if not problems:
            for r in receipts:
                if r["tool"] != "web_open_public" or r["status"] != "OK":
                    continue
                if (urlsplit(r["final_url"]).hostname or "") not in o.sources:
                    continue
                if o.pattern.search(page_text(kept[r["seq"]])):
                    hit = r["seq"]
                    break
        objectives.append((o.id, "VERIFIED" if hit else "NOT_VERIFIED", hit))
        if hit:
            support.setdefault(hit, []).append(o.id)
    n_ok = sum(1 for _, st, _ in objectives if st == "VERIFIED")
    verdict = ("RESEARCH_INVALID_EVIDENCE" if problems else "RESEARCH_VERIFIED" if n_ok == len(objectives)
               else "RESEARCH_PARTIAL" if n_ok else "RESEARCH_NOT_VERIFIED")
    sources = [{"seq": r["seq"], "url": r["final_url"], "fetched_at": r["fetched_at"], "sha256": r["sha256"],
                "bytes": r["bytes"], "supports": support.get(r["seq"], [])}
               for r in receipts if r["tool"] == "web_open_public" and r["status"] == "OK"]
    return {"verdict": verdict, "problems": problems, "objectives": objectives, "sources": sources,
            "claims": {o.id: o.claim for o in spec.objectives}}
