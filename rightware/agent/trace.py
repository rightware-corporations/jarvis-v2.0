"""Opt-in task trace for reconstructing an agent run (WORK-07 R3-C1). OFF by default.

When an ``AgentSession`` is created with ``trace=True`` this records, per model turn:
* turn number and a response id (hash of the response);
* tools offered;
* each proposal with its call id and sanitised arguments;
* the RIGHTWARE decision (approved / denied + reason);
* the execution status;
* the SHA-256 and length of what the tool returned to the model;
* for browser page loads, what the model was SHOWN: link ids in the first view, how many
  registered links were not shown, sanitised URL, truncation flags and a view hash.

It never stores page text, typed text, conversation messages, tokens or credentials. Arguments
go through the same reduction as the audit (URL -> host + hash, text -> length + hash). It
changes no decision: tracing only observes (tested: identical outcomes with tracing on and off).
Memory only: the product never writes it to disk; callers decide what to persist.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

from rightware.agent.policy import _safe_args


def _page_id(url: str) -> str:
    """Scheme + host + path: no query string (typed searches, keys) and no fragment."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{parts.path}" + ("?…" if parts.query else "")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TaskTrace:
    def __init__(self):
        self.turns: list[dict] = []
        self.final: dict = {}
        self._current: dict | None = None            # proposal awaiting its execution result

    # -- engine boundary -----------------------------------------------------------
    def on_generate(self, tools_offered: list, response: dict | None, halted: str | None = None) -> None:
        names = sorted(t.get("function", {}).get("name", "") for t in tools_offered or [] if isinstance(t, dict))
        if response is None:
            self.turns.append({"turn": len(self.turns) + 1, "response_id": None, "tools_offered": names,
                               "halted_before_model": halted, "proposals": [], "text_chars": 0})
            return
        calls = response.get("tool_calls") or []
        rid = _sha(json.dumps({"c": response.get("content") or "", "t": calls}, sort_keys=True, default=str))[:16]
        proposals = []
        for tc in calls:
            try:
                args = json.loads(tc.get("arguments") or "{}")
            except (TypeError, ValueError):
                args = None
            proposals.append({"call_id": str(tc.get("id", ""))[:64], "name": str(tc.get("name", ""))[:60],
                              "args": _safe_args(args) if isinstance(args, dict) else {"_raw": "<invalid>"},
                              "decision": None, "reason": None, "status": None})
        self.turns.append({"turn": len(self.turns) + 1, "response_id": rid, "tools_offered": names,
                           "proposals": proposals, "text_chars": len(response.get("content") or "")})

    # -- authorisation and execution --------------------------------------------------
    def _proposal(self, call_id: str, name: str) -> dict | None:
        for turn in reversed(self.turns):
            for p in turn["proposals"]:
                if p["call_id"] == str(call_id)[:64] and p["name"] == name and p["decision"] is None:
                    return p
        return None

    def on_decision(self, call_id: str, name: str, allowed: bool, reason: str | None, denial_text: str = "") -> None:
        p = self._proposal(call_id, name)
        if p is None:
            return
        p["decision"], p["reason"] = ("APPROVED" if allowed else "DENIED"), (None if allowed else reason)
        if allowed:
            self._current = p
        else:
            p["status"] = "DENIED"
            p["result_sha256"], p["result_chars"] = _sha(denial_text)[:16], len(denial_text)
            self._current = None

    def on_result(self, name: str, status: str, content: str, view: dict | None) -> None:
        p = self._current if self._current is not None and self._current["name"] == name else None
        if p is None:                         # a result with no traced approval: record it, never drop it
            p = {"call_id": None, "name": name, "args": {}, "decision": "UNTRACED", "reason": None}
            (self.turns[-1]["proposals"] if self.turns else []).append(p)
        p["status"] = status
        p["result_sha256"], p["result_chars"] = _sha(content)[:16], len(content)
        if view is not None:
            p["view"] = view
        self._current = None

    def on_not_executed(self, name: str) -> None:
        for turn in reversed(self.turns):
            for p in turn["proposals"]:
                if p["name"] == name and p["decision"] == "APPROVED" and p["status"] is None:
                    p["status"] = "NOT_EXECUTED"
                    return

    # -- summary ----------------------------------------------------------------------
    def finish(self, completion: str, halted: str | None, flags: list[str], sources: list[dict],
               browser=None) -> None:
        self.final = {"completion": completion, "halted": halted, "flags": list(flags),
                      "sources": [_page_id(s.get("final_url") or "") for s in sources], "turns": len(self.turns),
                      "links": self.link_visibility(browser)}

    def link_visibility(self, browser) -> dict:
        """Three distinct facts per link id: REGISTERED by the browser, PRESENTED to the model
        (first view of a page or a web_find result), USED in an executed operation."""
        registered = sorted(browser.links, key=lambda x: int(x[1:])) if browser is not None else []
        presented, used = set(), set()
        for turn in self.turns:
            for p in turn["proposals"]:
                view = p.get("view") or {}
                presented.update(view.get("shown_links", []))
                presented.update(view.get("find_matches", []))
                if p["name"] == "web_follow" and p.get("status") == "OK" and view.get("followed"):
                    used.add(view["followed"])
        key = lambda x: int(x[1:])  # noqa: E731
        return {"registered": len(registered), "presented": sorted(presented, key=key),
                "registered_not_presented": len([x for x in registered if x not in presented]),
                "used": sorted(used, key=key),
                "used_without_presentation": sorted(used - presented, key=key)}

    def as_dict(self) -> dict:
        return {"turns": self.turns, "final": self.final}
