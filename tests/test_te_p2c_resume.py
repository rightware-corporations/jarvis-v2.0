"""JRV-TE-P2C: supervised interruption, restart and resume behind the RIGHTWARE Tool Gateway (T2).

OFFLINE and deterministic (mock fixture, injected clocks, no goose, no model). Positive, negative and
adversarial cases for: host-authorised re-binding, identity separation (transport / task / operations),
anti-replay and de-duplication (READS and EFFECTS tested separately), in-flight interruption, cancellation,
quotas across the restart, tool/network containment and verification. Not real-model evidence.
"""
import copy
import http.server
import json
import pathlib
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

from labs.te_p2a_gateway import frozen_p2c
from labs.te_p2a_gateway import report_contract as RC

try:
    import httpx
    from labs.te_p1_bakeoff.site import PAGES
    from labs.te_p2a_gateway import fixture_transport as FT
    from labs.te_p2a_gateway import gateway as G
    from labs.te_p2a_gateway.gateway import Gateway
    from labs.te_p2a_gateway.mcp_http import McpApp, make_handler
    from labs.te_p2a_gateway.verify import verify
    from rightware.agent.policy import Budgets
except ImportError:                      # plain Python without the pinned vendor
    Gateway = None

BASE = "https://catalog.fixture.example/"
GOOSE, OTHER, LOOP = "172.30.10.10", "172.30.10.5", "127.0.0.1"
TOKEN = "t" * 48
GOOD = {"report_schema_version": RC.CONTRACT_ID, "recommendation": "TerraLens",
        "products": [{"name": "AtlasBoard", "mac_support": True, "csv_support": True, "offline": True,
                      "scheduled_automation": False, "price_usd_month": 0},
                     {"name": "NovaView", "mac_support": True, "csv_support": True, "offline": False,
                      "scheduled_automation": True, "price_usd_month": 9},
                     {"name": "TerraLens", "mac_support": True, "csv_support": True, "offline": True,
                      "scheduled_automation": True, "price_usd_month": 12}],
        "sources": [BASE, BASE + "catalog", BASE + "vendors/atlasboard", BASE + "vendors/novaview",
                    BASE + "vendors/terralens-factsheet"]}
SUMMARY = ("task_id", "attempt_id", "generation", "last_sequence", "receipts_sha256", "chain_head")


class NoNetwork:
    def __enter__(self):
        def boom(*a, **k):
            raise AssertionError("network access attempted in an offline test")
        self._p = [mock.patch.object(socket.socket, "connect", boom), mock.patch.object(socket, "getaddrinfo", boom)]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._p:
            p.stop()


@unittest.skipIf(Gateway is None, "pinned OpenJarvis venv required")
class _Resume(unittest.TestCase):
    network_guard = True

    def setUp(self):
        if self.network_guard:
            g = NoNetwork().__enter__()
            self.addCleanup(g.__exit__)
        self.events, self.flaky, self.now, self.delay = [], [0], [0.0], 0.0

        def handler(request):
            if self.delay:
                time.sleep(self.delay)
            path = request.url.path
            if path == "/vendors/terralens":
                self.flaky[0] += 1
                code = 503 if self.flaky[0] == 1 else 200
            else:
                code = 200 if path in PAGES else 404
            if path == "/private/secret":
                code = 403
            self.events.append({"path": path, "http_status": code})
            return httpx.Response(code, headers={"content-type": "text/html"},
                                  text=PAGES[path] if code == 200 else "unavailable")
        self.mock = httpx.MockTransport(handler)
        self.build()

    def build(self, task="TE-P2C-T2", attempt="C0", tool_timeout=5.0, token=TOKEN):
        self.gw = Gateway(task_id=task, attempt_id=attempt, sites=(FT.SYNTHETIC_HOST,),
                          fetcher=FT.fixture_fetcher(inner=self.mock),
                          budgets=Budgets(max_calls=15, deadline_seconds=1700), clock=lambda: self.now[0],
                          tool_timeout=tool_timeout, report_contract=RC.CONTRACT_ID)
        self.app = McpApp(self.gw, allowed_clients=(GOOSE,), control_token=token, clock=lambda: self.now[0])
        self.sid, self.rid = None, 0
        return self.app

    # -- transport emulation (same admission order as the HTTP handler) --------------------
    def post(self, method, params=None, rid="auto", ip=GOOSE, sid="current", app=None):
        app = app or self.app
        sid = self.sid if sid == "current" else sid
        if rid == "auto":
            self.rid += 1
            rid = self.rid
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if rid is not None:
            msg["id"] = rid
        denied = app.admit(ip, method, sid)
        if denied:
            return denied[0], denied[1]
        return 200, app.handle(msg)

    def init(self, ip=GOOSE, app=None):
        code, body = self.post("initialize", {"protocolVersion": "2025-06-18"}, rid=0, ip=ip, app=app)
        if code == 200 and "result" in (body or {}):
            self.sid = (app or self.app).session_id
        return code, body

    def call(self, tool, args, rid="auto", sid="current"):
        code, body = self.post("tools/call", {"name": tool, "arguments": args}, rid=rid, sid=sid)
        if code != 200:
            return code, None, None
        return code, body["result"]["content"][0]["text"], body["result"]["isError"]

    def ctl(self, action, body=None, ip=LOOP, token=TOKEN):
        return self.app.control(ip, token, action, body)

    def resume(self, ttl=120):
        code, snap = self.ctl("suspend")
        self.assertEqual(code, 200)
        code, grant = self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}, "ttl_seconds": ttl})
        self.assertEqual(code, 200, grant)
        self.rid = 0                                   # a new goose process restarts its JSON-RPC ids
        code, _ = self.init()
        self.assertEqual(code, 200)
        return snap

    @staticmethod
    def link(page, suffix):
        import re
        for line in page.splitlines():
            m = re.match(r"(L\d+): .* -> (\S+)$", line)
            if m and m.group(2).endswith(suffix):
                return m.group(1)
        raise AssertionError(suffix)

    def rest_of_mission(self, root_text):
        _, cat, _ = self.call("web_follow", {"link": self.link(root_text, "/catalog")})
        for suffix in ("/vendors/atlasboard", "/vendors/novaview", "/vendors/terralens", "/vendors/terralens-factsheet"):
            self.call("web_follow", {"link": self.link(cat, suffix)})

    def verdict(self):
        return verify(self.gw.receipts(), self.events, None, submissions=self.gw.submissions,
                      report_channel="submit_report")


# ------------------------------------------------------------------------------------------- legit
class LegitimateResume(_Resume):
    def test_interrupt_after_first_operation_then_resume_and_verify(self):
        self.init()
        old_sid = self.sid
        _, root, err = self.call("web_open", {"url": BASE})
        self.assertFalse(err)
        before = self.gw.receipts()
        snap = self.resume()
        self.assertEqual((snap["last_sequence"], snap["generation"], snap["in_flight"]), (1, 0, False))
        self.assertNotEqual(self.sid, old_sid)
        self.assertEqual(self.gw.generation, 1)
        self.rest_of_mission(root)                    # browser state survives (links L# still valid)
        code, fb, err = self.call("submit_report", {"report": json.dumps(GOOD)})
        self.assertEqual(json.loads(fb)["decision"], "ACCEPTED_FOR_VERIFICATION")
        receipts = self.gw.receipts()
        self.assertEqual(receipts[:len(before)], before)                       # history preserved
        self.assertEqual([r.sequence for r in receipts], list(range(1, len(receipts) + 1)))
        ids = [r.call_id for r in receipts]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(":g1:" in i for i in ids[len(before):]))
        self.assertNotIn(":g", ids[0])                                         # generation 0 format unchanged
        self.assertEqual(self.verdict()["verdict"], "TASK_VERIFIED_LIMITED")
        self.assertTrue(RC.check_chain(self.gw.submission_chain, receipts, self.gw.submissions)["valid"])
        self.assertEqual([e["event"] for e in self.app.control_log], ["suspended", "resume_authorized", "rebound"])

    def test_transport_state_invariants_across_suspend_and_rebind(self):
        import re
        self.init()
        old = self.sid
        self.ctl("suspend")
        self.assertIsNone(self.app.session_id)                        # terminated, not just flagged
        snap = self.gw.snapshot()
        self.ctl("authorize-resume", {k: snap[k] for k in SUMMARY})
        self.init()
        self.assertIsNone(self.app.grant)                             # single-use grant consumed
        self.assertFalse(self.app.suspended)
        self.assertRegex(self.app.session_id, r"^[0-9a-f]{32}$")      # fresh unpredictable id
        self.assertNotEqual(self.app.session_id, old)

    def test_interrupt_before_any_operation(self):
        self.init()
        snap = self.resume()
        self.assertEqual((snap["receipts"], snap["last_sequence"]), (0, 0))
        _, root, err = self.call("web_open", {"url": BASE})
        self.assertFalse(err)
        self.assertEqual(self.gw.receipts()[0].call_id, "TE-P2C-T2:C0:g1:1")

    def test_resume_can_happen_twice_with_fresh_authorisation(self):
        self.init()
        self.call("web_open", {"url": BASE})
        self.resume()
        self.call("web_open", {"url": BASE + "catalog"})
        self.resume()
        self.assertEqual(self.gw.generation, 2)
        self.call("web_follow", {"link": "L2"})
        ids = [r.call_id for r in self.gw.receipts()]
        self.assertEqual(len(ids), len(set(ids)))


# ------------------------------------------------------------------------------------------- identity
class RebindIdentity(_Resume):
    def test_old_forged_and_missing_session_ids_are_refused(self):
        self.init()
        old = self.sid
        self.ctl("suspend")
        self.assertEqual(self.call("web_open", {"url": BASE}, sid=old)[0], 404)          # terminated
        self.assertEqual(self.call("web_open", {"url": BASE}, sid="f" * 32)[0], 404)
        self.assertEqual(self.call("web_open", {"url": BASE}, sid=None)[0], 400)
        self.assertEqual(self.init()[0], 409)                                             # no grant
        snap = self.gw.snapshot()
        self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}})
        self.init()
        self.assertEqual(self.call("web_open", {"url": BASE}, sid=old)[0], 404)          # old id stays dead
        self.assertEqual(self.gw.receipts(), ())

    def test_grant_is_single_use_and_expires(self):
        self.init()
        self.ctl("suspend")
        snap = self.gw.snapshot()
        self.assertEqual(self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}, "ttl_seconds": 10})[0], 200)
        self.now[0] += 11
        self.assertEqual(self.init(), (403, "resume grant expired"))
        self.assertEqual(self.init()[0], 409)                                             # grant gone
        self.assertTrue(self.app.suspended)
        self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}, "ttl_seconds": 10})
        self.assertEqual(self.init()[0], 200)
        self.assertEqual(self.init()[0], 409)                                             # consumed
        for ttl in (0, -1, 301, "60", True, 1.5):
            with self.subTest(ttl=ttl):
                self.ctl("suspend")
                s = self.gw.snapshot()
                self.assertEqual(self.ctl("authorize-resume", {**{k: s[k] for k in SUMMARY}, "ttl_seconds": ttl})[0], 400)

    def test_concurrent_reinitialize_consumes_the_grant_once(self):
        self.init()
        self.ctl("suspend")
        s = self.gw.snapshot()
        self.ctl("authorize-resume", {**{k: s[k] for k in SUMMARY}})
        self.assertIsNone(self.app.admit(GOOSE, "initialize", None))
        self.assertIsNone(self.app.admit(GOOSE, "initialize", None))                    # both admitted…
        first = self.app.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        second = self.app.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        self.assertIn("result", first)
        self.assertIn("error", second)                                                    # …one re-binds
        self.assertEqual(self.gw.generation, 1)

    def test_summary_mismatch_stale_or_other_task_is_refused(self):
        self.init()
        self.call("web_open", {"url": BASE})
        code, snap = self.ctl("suspend")
        tampered = {"task_id": "OTHER-TASK", "attempt_id": "C9", "generation": 1, "last_sequence": 0,
                    "receipts_sha256": "0" * 64, "chain_head": "f" * 64}
        for key, bad in tampered.items():
            with self.subTest(field=key):
                code, body = self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}, key: bad})
                self.assertEqual((code, body["fields"]), (409, [key]))
                self.assertIsNone(self.app.grant)
        self.assertEqual(self.ctl("authorize-resume", {})[0], 409)
        stale = {k: snap[k] for k in SUMMARY}
        self.ctl("authorize-resume", stale)
        self.init()
        self.call("web_open", {"url": BASE + "catalog"})
        self.ctl("suspend")
        self.assertEqual(self.ctl("authorize-resume", stale)[0], 409)                     # stale summary
        self.assertFalse(any(e["event"] == "resume_authorized" and e["generation"] == 1 for e in self.app.control_log))

    def test_session_of_another_task_is_not_accepted(self):
        self.init()
        a_sid, a_app = self.sid, self.app
        other_gw = Gateway(task_id="OTHER", attempt_id="X1", sites=(FT.SYNTHETIC_HOST,),
                           fetcher=FT.fixture_fetcher(inner=self.mock), budgets=Budgets(), report_contract=RC.CONTRACT_ID)
        b = McpApp(other_gw, allowed_clients=(GOOSE,), control_token=TOKEN)
        b.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        self.assertEqual(b.admit(GOOSE, "tools/call", a_sid), (404, "unknown session id"))
        a_app.control(LOOP, TOKEN, "suspend", None)
        snap = a_app.gateway.snapshot()
        b.control(LOOP, TOKEN, "suspend", None)
        self.assertEqual(b.control(LOOP, TOKEN, "authorize-resume", {k: snap[k] for k in SUMMARY})[0], 409)

    def test_control_is_host_only(self):
        for ip, token in ((GOOSE, TOKEN), (OTHER, TOKEN), (LOOP, "wrong"), (LOOP, None), (LOOP, ""), ("::1", TOKEN)):
            with self.subTest(ip=ip, token=token):
                self.assertEqual(self.ctl("suspend", ip=ip, token=token)[0], 403)
        self.assertFalse(self.app.suspended)
        self.assertEqual(self.ctl("bogus")[0], 404)
        self.assertEqual(self.ctl("authorize-resume", {})[0], 409)                        # not suspended
        disabled = McpApp(self.gw, allowed_clients=(GOOSE,))
        self.assertEqual(disabled.control(LOOP, TOKEN, "suspend", None)[0], 404)
        self.assertEqual(self.post("initialize", rid=0, ip=OTHER)[0], 403)                # client allowlist kept

    def test_lost_connection_needs_host_suspension(self):
        self.init()
        self.call("web_open", {"url": BASE})
        self.rid = 0                                                    # executor died without supervision
        self.assertEqual(self.init()[0], 409)                           # fail closed: no silent re-bind
        self.resume()
        self.assertEqual(self.call("web_open", {"url": BASE + "catalog"})[0], 200)

    def test_generation_must_advance_by_one(self):
        with self.assertRaises(ValueError):
            self.gw.begin_generation(2)
        with self.assertRaises(ValueError):
            self.gw.begin_generation(0)


# ------------------------------------------------------------------------------------------- replay
class ReplayAndDedup(_Resume):
    def test_completed_read_is_replayed_once_not_refetched(self):
        self.init()
        _, root, _ = self.call("web_open", {"url": BASE})
        self.resume()
        calls_before = self.gw.policy.calls
        code, text, err = self.call("web_open", {"url": BASE})
        self.assertFalse(err)
        self.assertIn("não re-executado", text)
        self.assertIn(root, text)
        self.assertEqual([e["path"] for e in self.events], ["/"])                         # no second HTTP request
        r = self.gw.receipts()[-1]
        self.assertEqual((r.authorized, r.executed, r.reason_code), (False, False, "REPLAYED_FROM_RECEIPT"))
        self.assertEqual(self.gw.policy.calls, calls_before)                              # no budget consumed
        self.call("web_open", {"url": BASE})                                               # READ: one replay only
        self.assertEqual([e["path"] for e in self.events], ["/", "/"])
        self.assertTrue(self.gw.receipts()[-1].executed)
        self.assertEqual(self.gw.replays, [{"sequence": 2, "original_sequence": 1, "tool": "web_open", "generation": 1,
                                            "served": True}])

    def test_follow_and_open_of_the_same_page_are_the_same_operation(self):
        self.init()
        _, root, _ = self.call("web_open", {"url": BASE})
        self.call("web_follow", {"link": self.link(root, "/catalog")})
        self.resume()
        self.call("web_open", {"url": BASE + "catalog"})
        self.assertEqual([e["path"] for e in self.events], ["/", "/catalog"])

    def test_failed_read_is_not_replayed(self):
        self.init()
        _, root, _ = self.call("web_open", {"url": BASE})
        _, cat, _ = self.call("web_follow", {"link": self.link(root, "/catalog")})
        _, _, err = self.call("web_follow", {"link": self.link(cat, "/vendors/terralens")})
        self.assertTrue(err)                                                               # 503
        self.resume()
        _, text, err = self.call("web_follow", {"link": self.link(cat, "/vendors/terralens")})
        self.assertFalse(err)
        self.assertEqual(self.events[-1], {"path": "/vendors/terralens", "http_status": 200})

    def test_same_generation_is_unchanged(self):
        self.init()
        self.call("web_open", {"url": BASE})
        self.call("web_open", {"url": BASE})
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.gw.replays, [])

    def test_same_generation_after_resume_is_unchanged(self):
        self.init()
        self.resume()
        self.call("web_open", {"url": BASE})
        self.call("web_open", {"url": BASE})                          # both in generation 1: normal policy
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.gw.replays, [])

    def count_effects(self):
        real = self.gw._runners["submit_report"]
        self.effects = []

        def counted(**kw):
            self.effects.append(kw)
            return real(**kw)
        self.gw._runners["submit_report"] = counted

    def test_effect_is_never_executed_twice_across_restart(self):
        self.count_effects()
        self.init()
        self.call("submit_report", {"report": json.dumps(GOOD)})
        self.assertEqual(len(self.effects), 1)
        self.resume()
        for i in range(G.EFFECT_REPLAY_LIMIT):
            _, text, err = self.call("submit_report", {"report": json.dumps(GOOD)})
            self.assertIn("não re-executado", text)
        _, text, err = self.call("submit_report", {"report": json.dumps(GOOD)})
        self.assertTrue(err)
        self.assertEqual(self.gw.receipts()[-1].reason_code, "EFFECT_ALREADY_EXECUTED")
        self.assertEqual(len(self.effects), 1)                                            # EFFECT: never again
        self.assertEqual(len(self.gw.submission_chain), 1)
        self.assertTrue(RC.check_chain(self.gw.submission_chain, self.gw.receipts(), self.gw.submissions)["valid"])
        self.assertEqual(self.gw.policy.per_tool["submit_report"], 1)

    def test_refused_effect_is_also_not_reexecuted(self):
        self.count_effects()
        self.init()
        bad = json.dumps({**GOOD, "extra": 1})
        self.call("submit_report", {"report": bad})
        self.resume()
        _, text, err = self.call("submit_report", {"report": bad})
        self.assertIn("não re-executado", text)
        self.assertTrue(err)
        self.assertEqual(len(self.effects), 1)
        self.call("submit_report", {"report": json.dumps(GOOD)})                           # a NEW report is new
        self.assertEqual(len(self.effects), 2)
        self.assertEqual(len(self.gw.submissions), 1)

    def test_read_safety_does_not_imply_effect_safety(self):
        """The same repeat that is allowed for a read (after one replay) is never allowed for an effect."""
        self.count_effects()
        self.init()
        self.call("web_open", {"url": BASE})
        self.call("submit_report", {"report": json.dumps(GOOD)})
        self.resume()
        for _ in range(2):
            self.call("web_open", {"url": BASE})
            self.call("submit_report", {"report": json.dumps(GOOD)})
        self.assertEqual(sum(e["path"] == "/" for e in self.events), 2)                   # read re-executed once
        self.assertEqual(len(self.effects), 1)                                            # effect never


# ------------------------------------------------------------------------------------------- in flight
class InFlightAndCancel(_Resume):
    def test_suspend_waits_for_an_operation_in_progress(self):
        self.init()
        self.delay = 0.4
        t = threading.Thread(target=self.call, args=("web_open", {"url": BASE}))
        t.start()
        time.sleep(0.1)
        code, snap = self.ctl("suspend")                    # blocks until the call has finished and is receipted
        t.join()
        self.assertEqual((snap["last_sequence"], snap["in_flight"]), (1, False))
        self.assertEqual(self.gw.receipts()[0].status, "OK")
        self.delay = 0.0
        self.resume()
        self.call("web_open", {"url": BASE})
        self.assertEqual(len(self.events), 1)                                              # replayed, not refetched

    def test_tool_still_running_after_timeout_blocks_resume(self):
        self.build(tool_timeout=0.2)
        self.init()
        self.delay = 0.8
        _, text, err = self.call("web_open", {"url": BASE})
        self.assertTrue(err)
        code, snap = self.ctl("suspend")
        self.assertTrue(snap["in_flight"])
        code, body = self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}})
        self.assertEqual((code, body["error"]), (409, "an operation is still in flight"))
        time.sleep(0.9)
        snap = self.gw.snapshot()
        self.assertFalse(snap["in_flight"])
        r = self.gw.receipts()[0]
        self.assertEqual((r.status, r.late), ("OK", True))                                 # finished late, receipted
        self.assertEqual(self.ctl("authorize-resume", {**{k: snap[k] for k in SUMMARY}})[0], 200)
        self.rid = 0
        self.init()
        _, text, err = self.call("web_open", {"url": BASE})
        self.assertEqual(len(self.events), 1)                                              # never two executions
        self.assertEqual([r.binding for r in self.gw.receipts()], ["BOUND", "BOUND"])

    def test_cancellations_do_not_leak_across_generations(self):
        self.init()
        self.post("notifications/cancelled", {"requestId": 1}, rid=None)
        self.assertEqual(self.call("web_open", {"url": BASE}, rid=1)[2], True)             # refused (gen 0)
        self.resume()
        _, text, err = self.call("web_open", {"url": BASE}, rid=1)                         # same id, new process
        self.assertFalse(err)
        self.post("notifications/cancelled", {"requestId": 2}, rid=None)
        self.assertTrue(self.call("web_open", {"url": BASE + "catalog"}, rid=2)[2])
        self.assertEqual([r.status for r in self.gw.receipts()], ["DENIED", "OK", "DENIED"])

    def test_cancel_task_during_suspension_holds(self):
        self.init()
        self.call("web_open", {"url": BASE})
        snap = self.resume()
        self.gw.cancel()
        _, text, err = self.call("web_open", {"url": BASE + "catalog"})
        self.assertTrue(err)
        self.assertEqual(self.gw.receipts()[-1].status, "DENIED")


# ------------------------------------------------------------------------------------------- policy
class PolicyAcrossRestart(_Resume):
    def test_quotas_and_budget_accumulate(self):
        self.init()
        self.call("web_open", {"url": BASE})
        self.call("web_open", {"url": BASE + "catalog"})
        calls = self.gw.policy.calls
        self.resume()
        self.assertEqual(self.gw.policy.calls, calls)
        self.call("web_open", {"url": BASE + "vendors/novaview"})                         # 3rd web_open allowed
        _, text, err = self.call("web_open", {"url": BASE + "vendors/atlasboard"})         # 4th: quota (3)
        self.assertTrue(err)
        self.assertEqual(self.gw.receipts()[-1].reason_code, "TOOL_QUOTA")

    def test_unauthorised_tools_and_hosts_stay_blocked(self):
        self.init()
        self.resume()
        for name in ("load_skill", "developer__shell", "web_type"):
            with self.subTest(name=name):
                _, text, err = self.call(name, {"name": "x"})
                self.assertTrue(err)
                self.assertFalse(self.gw.receipts()[-1].executed)
        _, text, err = self.call("web_open", {"url": "https://example.com/"})
        self.assertTrue(err)
        self.assertEqual(self.events, [])
        names = [t["name"] for t in self.post("tools/list")[1]["result"]["tools"]]
        self.assertEqual(names, ["web_open", "web_follow", "web_find", "submit_report"])

    def test_report_without_matching_evidence_is_not_verified(self):
        self.init()
        self.call("web_open", {"url": BASE})
        self.resume()
        self.call("submit_report", {"report": json.dumps(GOOD)})          # claims pages it never read
        self.assertEqual(self.verdict()["verdict"], "NOT_VERIFIED")

    def test_tampered_agent_history_cannot_create_evidence(self):
        """After resume the agent behaves as if its (tampered) history said all pages were read."""
        self.init()
        self.resume()
        self.call("submit_report", {"report": json.dumps(GOOD)})
        v = self.verdict()
        self.assertEqual(v["verdict"], "NOT_VERIFIED")
        self.assertEqual([o[1] for o in v["objectives"]], ["MISSING"] * 4)


# ------------------------------------------------------------------------------------------- HTTP
class LoopbackHttp(_Resume):
    network_guard = False                                  # real loopback sockets only

    def test_control_over_http_needs_token_and_session_header_rules_hold(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def post(path, body, headers=None):
            req = urllib.request.Request(base + path, json.dumps(body).encode(),
                                         {"Content-Type": "application/json", **(headers or {})})
            try:
                r = opener.open(req, timeout=10)
                return r.status, json.loads(r.read() or b"null")
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"null")
        self.assertEqual(post("/control/suspend", {})[0], 403)
        self.assertEqual(post("/control/suspend", {}, {"X-Rightware-Control": "nope"})[0], 403)
        code, snap = post("/control/status", {}, {"X-Rightware-Control": TOKEN})
        self.assertEqual((code, snap["generation"], snap["suspended"]), (200, 0, False))
        self.assertNotIn(TOKEN, json.dumps(self.app.control_log))


# ------------------------------------------------------------------------------------------- runner rules
class RunnerRules(unittest.TestCase):
    def test_duplicate_effect_counts_only_accepted_submissions(self):
        from labs.te_p2a_gateway import te_p2c_resume as R
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d)
            rows = [{"sequence": 1, "tool": "web_open", "executed": True, "status": "OK", "http_status": 200,
                     "final_url": BASE, "call_id": "T:C:3"},
                    {"sequence": 2, "tool": "web_open", "executed": False, "status": "DENIED", "http_status": None,
                     "final_url": None, "call_id": "T:C:g1:3"}]
            (out / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            (out / "control.jsonl").write_text(json.dumps({"event": "rebound"}) + "\n")
            run = {"contract": {"submissions": [{"report_sha256": "a", "decision": "ACCEPTED_FOR_VERIFICATION"},
                                                {"report_sha256": "a", "decision": "ALREADY_ACCEPTED"}]}}
            c = R.continuity(out, {"last_sequence": 1}, run)
            self.assertEqual((c["duplicate_effects"], c["refused_repeat_submissions"]), (0, 1))
            self.assertEqual((c["rebound_events"], c["call_ids_unique"], c["sequence_contiguous"]), (1, True, True))
            run["contract"]["submissions"][1]["decision"] = "ACCEPTED_FOR_VERIFICATION"
            self.assertEqual(R.continuity(out, {"last_sequence": 1}, run)["duplicate_effects"], 1)
            rows.append({"sequence": 3, "tool": "web_open", "executed": True, "status": "OK", "http_status": 200,
                         "final_url": BASE, "call_id": "T:C:g1:4"})
            (out / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual(R.continuity(out, {"last_sequence": 1}, run)["reexecuted_completed_reads_after_resume"], [3])

    def run_row(self, verdict="TASK_VERIFIED_LIMITED", non_gw=(), chain=True, accepted=True):
        return {"verification": {"verdict": verdict, "http_receipt_correspondence": {"match": True}, "receipt_defects": []},
                "contract": {"chain_check_with_verdict": {"valid": chain},
                             "submissions": [{"decision": "ACCEPTED_FOR_VERIFICATION" if accepted else "REJECTED_SCHEMA"}]},
                "goose_tool_calls": {"non_gateway_calls": list(non_gw)},
                "inventory": {"only_gateway_tools_reach_model": True, "model_requests": 5}}

    def test_classification_and_decision(self):
        from labs.te_p2a_gateway import te_p2c_resume as R
        good = {"rebound_events": 1, "phase2_gateway_calls": 4, "duplicate_effects": 0, "call_ids_unique": True,
                "sequence_contiguous": True, "reexecuted_completed_reads_after_resume": []}
        alive = {"ollama": True}
        self.assertIsNone(R.classify(self.run_row(), good, alive, True, True)["category"])
        c = R.classify(self.run_row(), {**good, "duplicate_effects": 1}, alive, True, True)
        self.assertEqual((c["category"], c["critical_stop"], c["invalid"]), ("EFEITO_DUPLICADO", True, False))
        c = R.classify(self.run_row(non_gw=["load_skill"]), good, alive, True, True)
        self.assertEqual((c["category"], c["critical_stop"]), ("POLÍTICA", True))
        self.assertEqual(R.classify(self.run_row(), good, alive, True, False)["category"], "POLÍTICA")
        self.assertEqual(R.classify(self.run_row(), {**good, "rebound_events": 0}, alive, True, True)["category"],
                         "CONTINUIDADE")
        self.assertEqual(R.classify(self.run_row(), {**good, "reexecuted_completed_reads_after_resume": [3]}, alive,
                                    True, True)["category"], "LEITURA_REPETIDA")
        self.assertEqual(R.classify(self.run_row(), good, alive, False, True)["category"], "SEM_PONTO_DE_INTERRUPÇÃO")
        c = R.classify(self.run_row(verdict="NOT_VERIFIED", accepted=False), good, alive, True, True)
        self.assertEqual((c["category"], c["invalid"]), ("MODELO_FORMATO", False))
        self.assertEqual(R.classify(self.run_row(verdict="NOT_VERIFIED"), good, alive, True, True)["category"],
                         "MODELO_CONTEÚDO")
        c = R.classify(self.run_row(chain=False), good, alive, True, True)
        self.assertEqual((c["category"], c["invalid"]), ("HARNESS", True))
        c = R.classify(self.run_row(), good, {"ollama": False}, True, True)
        self.assertEqual((c["category"], c["invalid"]), ("AMBIENTE", True))

        row = lambda a, cat, resumed=True, crit=False: {"attempt": a, "category": cat, "resumed": resumed,
                                                        "invalid": False, "critical_stop": crit}
        self.assertEqual(R.summary([row("C1", None), row("C2", None), row("C3", None)])["decision_by_preregistered_rule"], "GO")
        self.assertEqual(R.summary([row("C1", None), row("C2", "MODELO_CONTEÚDO"), row("C3", None)])
                         ["decision_by_preregistered_rule"], "GO_CONDICIONAL")
        self.assertEqual(R.summary([row("C1", None), row("C2", "LEITURA_REPETIDA"), row("C3", None)])
                         ["decision_by_preregistered_rule"], "NO-GO")
        self.assertEqual(R.summary([row("C1", None), row("C2", "CONTINUIDADE", resumed=False), row("C3", None)])
                         ["decision_by_preregistered_rule"], "NO-GO")
        self.assertEqual(R.summary([row("C1", "EFEITO_DUPLICADO", crit=True)])["decision_by_preregistered_rule"], "NO-GO")
        self.assertEqual(R.summary([row("C1", None)])["decision_by_preregistered_rule"], "INCOMPLETE")


class FrozenP2C(unittest.TestCase):
    def test_frozen_set_unchanged(self):
        self.assertEqual(frozen_p2c.differences(), [])
        m = json.loads(frozen_p2c.MANIFEST.read_text())
        self.assertEqual(frozen_p2c.differences({**m, "files": {**m["files"],
                                                                "labs/te_p2a_gateway/report_contract.py": "0" * 64}}),
                         ["labs/te_p2a_gateway/report_contract.py"])


del _Resume

if __name__ == "__main__":
    unittest.main()
