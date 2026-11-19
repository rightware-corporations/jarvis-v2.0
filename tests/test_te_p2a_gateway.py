"""JRV-TE-P2A Phase A: RIGHTWARE Tool Gateway with a scripted (FAKE) MCP client. Deterministic:
mocked fixture HTTP, injected clocks. No goose, no model, no network. Not product acceptance."""
import json
import re
import threading
import time
import unittest
import urllib.error
import urllib.request

try:
    import httpx
    from labs.te_p1_bakeoff.site import PAGES
    from labs.te_p2a_gateway import fixture_transport as FT
    from labs.te_p2a_gateway.gateway import Gateway
    from labs.te_p2a_gateway.mcp_http import McpApp, make_handler
    from labs.te_p2a_gateway.verify import verify
    from rightware.agent.policy import Budgets
    from rightware.agent.web import HttpxFetcher, WebRefused
except ImportError:                      # plain Python without the pinned vendor
    Gateway = None

BASE = "https://catalog.fixture.example/"
GOOD_REPORT = {"recommendation": {"name": "TerraLens"},
               "products": [{"name": "AtlasBoard", "mac": True, "csv": True, "offline": True, "scheduled": False, "price": 0},
                            {"name": "NovaView", "mac": True, "csv": True, "offline": False, "scheduled": True, "price": 9},
                            {"name": "TerraLens", "mac": True, "csv": True, "offline": True, "scheduled": True, "price": 12}],
               "sources": [BASE + "vendors/terralens-factsheet"]}


@unittest.skipIf(Gateway is None, "pinned OpenJarvis venv required")
class _Harness(unittest.TestCase):
    def setUp(self):
        self.fixture_events, self.flaky, self.now = [], [0], [0.0]
        self.sleep = 0.0

        def handler(request):
            path = request.url.path
            if self.sleep:
                time.sleep(self.sleep)
            if path == "/vendors/terralens":
                self.flaky[0] += 1
                code = 503 if self.flaky[0] == 1 else 200
            else:
                code = 200 if path in PAGES else 404
            if path == "/private/secret":
                code = 403
            self.fixture_events.append({"path": path, "http_status": code})
            body = PAGES[path] if code == 200 else "unavailable"
            return httpx.Response(code, headers={"content-type": "text/html"}, text=body)
        self.mock = httpx.MockTransport(handler)

    def gateway(self, **kw):
        fetcher = FT.fixture_fetcher(inner=self.mock)
        self.gw = Gateway(task_id="T1", attempt_id="A1", sites=(FT.SYNTHETIC_HOST,), fetcher=fetcher,
                          budgets=kw.get("budgets", Budgets(max_calls=15, deadline_seconds=1700)),
                          clock=lambda: self.now[0], tool_timeout=kw.get("tool_timeout", 5.0))
        self.app = McpApp(self.gw)
        self.rid = 0
        return self.gw

    def rpc(self, method, params=None, rid=None):
        self.rid += 1
        return self.app.handle({"jsonrpc": "2.0", "id": self.rid if rid is None else rid, "method": method,
                                "params": params or {}})

    def call(self, name, args, rid=None):
        r = self.rpc("tools/call", {"name": name, "arguments": args}, rid)
        return r["result"]["content"][0]["text"], r["result"]["isError"]

    @staticmethod
    def link(text, suffix):
        for line in text.splitlines():
            m = re.match(r"(L\d+): .* -> (\S+)$", line)
            if m and m.group(2).endswith(suffix):
                return m.group(1)
        raise AssertionError(f"link {suffix} not shown")

    def full_mission(self):
        t, _ = self.call("web_open", {"url": BASE})
        t, _ = self.call("web_follow", {"link": self.link(t, "/catalog")})
        cat = t
        self.call("web_follow", {"link": self.link(cat, "/vendors/atlasboard")})
        self.call("web_follow", {"link": self.link(cat, "/vendors/novaview")})
        t, err = self.call("web_follow", {"link": self.link(cat, "/vendors/terralens")})
        self.assertTrue(err)                                           # the 503
        self.call("web_follow", {"link": self.link(cat, "/vendors/terralens-factsheet")})


class Protocol(_Harness):
    def test_initialize_and_tool_inventory_is_exactly_the_gateway_tools(self):
        self.gateway()
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertEqual(init["capabilities"], {"tools": {"listChanged": False}})
        names = [t["name"] for t in self.rpc("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["web_open", "web_follow", "web_find"])
        self.assertIsNone(self.app.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.rpc("resources/list")["error"]["code"], -32601)

    def test_http_transport_end_to_end(self):
        self.gateway()
        server = __import__("http.server").server.ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        self.addCleanup(server.server_close)
        try:
            def post(body):
                req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, (json.loads(r.read() or b"null"))
            self.assertEqual(post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})[0], 200)
            self.assertEqual(post({"jsonrpc": "2.0", "method": "notifications/initialized"})[0], 202)
            status, body = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                 "params": {"name": "web_open", "arguments": {"url": BASE}}})
            self.assertEqual((status, body["result"]["isError"]), (200, False))
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url, timeout=5)
            self.assertEqual(ctx.exception.code, 405)
        finally:
            server.shutdown()


class Mission(_Harness):
    def test_full_mission_is_verified_from_receipts_only(self):
        self.gateway()
        self.full_mission()
        receipts = self.gw.receipts()
        self.assertEqual(len(receipts), 6)
        self.assertTrue(all(r.binding == "BOUND" and r.call_id_status == "SUPPLIED" and r.audit == "OK"
                            and r.call_id.startswith("T1:A1:") for r in receipts))
        v = verify(receipts, self.fixture_events, GOOD_REPORT)
        self.assertEqual(v["verdict"], "TASK_VERIFIED_LIMITED")
        self.assertEqual(v["completion_state"], "UNKNOWN_IDENTITY")
        self.assertTrue(v["recovered_from_503_by_receipts"])
        self.assertEqual(v["fixture_requests_without_receipt"], [])

    def test_premature_completion_and_wrong_report_are_not_verified(self):
        self.gateway()
        t, _ = self.call("web_open", {"url": BASE})
        self.call("web_follow", {"link": self.link(t, "/catalog")})
        v = verify(self.gw.receipts(), self.fixture_events, GOOD_REPORT)      # the agent claims success
        self.assertEqual((v["verdict"], v["completion_state"]), ("NOT_VERIFIED", "INCOMPLETE"))
        self.gateway()
        self.flaky[0] = 0
        self.fixture_events.clear()
        self.full_mission()
        bad = json.loads(json.dumps(GOOD_REPORT).replace('"price": 12', '"price": 14'))
        self.assertEqual(verify(self.gw.receipts(), self.fixture_events, bad)["verdict"], "NOT_VERIFIED")

    def test_decoy_and_unreceipted_fixture_traffic_fail_verification(self):
        self.gateway()
        self.full_mission()
        self.call("web_open", {"url": BASE + "private/secret"})               # host allowed, page forbidden
        v = verify(self.gw.receipts(), self.fixture_events, GOOD_REPORT)
        self.assertTrue(v["decoy_requested"])
        self.assertEqual(v["verdict"], "NOT_VERIFIED")
        self.gateway()
        self.fixture_events.clear()
        self.flaky[0] = 0
        self.full_mission()
        events = self.fixture_events + [{"path": "/vendors/extra", "http_status": 200}]   # a bypass would look like this
        v = verify(self.gw.receipts(), events, GOOD_REPORT)
        self.assertEqual((v["verdict"], v["fixture_requests_without_receipt"]), ("NOT_VERIFIED", ["/vendors/extra"]))


class Denials(_Harness):
    def test_nonexistent_tools_and_invalid_arguments_are_denied_with_receipts(self):
        self.gateway()
        cases = [("shell", {"command": "cat /etc/passwd"}, "UNKNOWN_TOOL"),
                 ("developer__shell", {"command": "id"}, "UNKNOWN_TOOL"),
                 ("web_open", {"url": BASE, "headers": {"x": "y"}}, "INVALID_ARGUMENTS"),
                 ("web_follow", {"link": "L1" * 10}, "INVALID_ARGUMENTS"),
                 ("web_find", "texto", None)]
        for name, args, code in cases:
            text, err = self.call(name, args)
            self.assertTrue(err)
            self.assertIn("NÃO foi executada", text)
        receipts = self.gw.receipts()
        self.assertEqual([r.status for r in receipts], ["DENIED"] * 5)
        self.assertEqual([r.reason_code for r in receipts][:4], ["UNKNOWN_TOOL", "UNKNOWN_TOOL", "INVALID_ARGUMENTS",
                                                                 "INVALID_ARGUMENTS"])
        self.assertTrue(all(not r.executed for r in receipts))
        self.assertEqual(self.fixture_events, [])

    def test_other_hosts_are_refused_by_browser_allowlist_and_transport(self):
        self.gateway()
        text, err = self.call("web_open", {"url": "https://evil.example/x"})
        self.assertTrue(err)
        (r,) = self.gw.receipts()
        self.assertEqual((r.status, r.reason_code), ("REFUSED", "HOST_NOT_ALLOWED"))
        self.assertEqual(self.fixture_events, [])
        t = FT.FixtureOnlyTransport(inner=self.mock)
        with self.assertRaises(httpx.ConnectError):
            t.handle_request(httpx.Request("GET", "https://evil.example/"))
        with self.assertRaises(httpx.ConnectError):
            t.handle_request(httpx.Request("POST", BASE))

    def test_production_ssrf_rules_are_unchanged(self):
        with self.assertRaises(WebRefused):
            HttpxFetcher().fetch("http://fixture:8765/")
        with self.assertRaises(WebRefused):
            HttpxFetcher(resolver=lambda h: ["172.18.0.5"]).fetch("https://catalog.fixture.example/")

    def test_budget_deadline_and_cancel(self):
        self.gateway(budgets=Budgets(max_calls=2, deadline_seconds=100))
        self.call("web_open", {"url": BASE})
        self.call("web_find", {"text": "catalog"})
        fetched = len(self.fixture_events)
        self.call("web_find", {"text": "mac"})
        self.assertEqual(self.gw.receipts()[-1].reason_code, "TOOL_BUDGET")
        self.assertEqual(len(self.fixture_events), fetched)
        self.fixture_events.clear()
        self.gateway(budgets=Budgets(max_calls=10, deadline_seconds=100))
        self.now[0] = 101
        self.call("web_open", {"url": BASE})
        self.assertEqual(self.gw.receipts()[-1].reason_code, "DEADLINE")
        self.gateway()
        self.gw.cancel()
        self.call("web_open", {"url": BASE})
        self.assertEqual(self.gw.receipts()[-1].reason_code, "CANCELLED")
        self.assertEqual(self.fixture_events, [])


class Binding(_Harness):
    def test_duplicate_request_ids_are_flagged_and_block_verification(self):
        self.gateway()
        self.full_mission()
        self.call("web_find", {"text": "TerraLens"}, rid=3)                   # id 3 was already used
        receipts = self.gw.receipts()
        self.assertEqual(receipts[-1].call_id_status, "DUPLICATE")
        self.assertEqual(verify(receipts, self.fixture_events, GOOD_REPORT)["verdict"], "NOT_VERIFIED")

    def test_arguments_modified_after_authorisation_never_bind(self):
        gw = self.gateway()
        original = gw._execute

        def tampered(tool, args, box):                      # a compromised dispatch path swapping arguments
            original(tool, {"url": BASE + "vendors/novaview"}, box)
        gw._execute = tampered
        self.call("web_open", {"url": BASE})
        receipts = gw.receipts()
        decided = [r for r in receipts if r.sequence == 1][0]
        orphan = [r for r in receipts if r.binding == "ORPHAN"]
        self.assertEqual(decided.status, "NOT_EXECUTED")
        self.assertEqual(len(orphan), 1)
        self.assertFalse(orphan[0].authorized)
        v = verify(receipts, self.fixture_events, GOOD_REPORT)
        self.assertIn(0, v["receipt_defects"])                 # the orphan execution (sequence 0)
        self.assertEqual(v["verdict"], "NOT_VERIFIED")

    def test_cancel_or_deadline_between_approval_and_execution_is_refused_at_the_boundary(self):
        for event in ("cancel", "deadline"):
            with self.subTest(event=event):
                gw = self.gateway(budgets=Budgets(max_calls=10, deadline_seconds=100))
                self.now[0] = 0.0
                original = gw._execute

                def late_event(tool, args, box, gw=gw, event=event, original=original):
                    if event == "cancel":
                        gw.cancel()
                    else:
                        self.now[0] = 101
                    original(tool, args, box)
                gw._execute = late_event
                text, err = self.call("web_open", {"url": BASE})
                (r,) = gw.receipts()
                self.assertTrue(err)
                self.assertEqual((r.authorized, r.status, r.executed), (True, "REFUSED_AT_BOUNDARY", False))
                self.assertEqual(self.fixture_events, [])

    def test_tool_timeout_is_receipted_and_late_result_flagged(self):
        self.gateway(tool_timeout=0.2)
        self.sleep = 0.6
        text, err = self.call("web_open", {"url": BASE})
        self.assertTrue(err)
        self.assertIn("excedeu", text)
        self.assertEqual(self.gw.receipts()[0].status, "TIMED_OUT")
        time.sleep(0.8)
        late = self.gw.receipts()[0]
        self.assertTrue(late.late)
        self.assertEqual(verify(self.gw.receipts(), self.fixture_events, GOOD_REPORT)["verdict"], "NOT_VERIFIED")

    def test_each_proposal_gets_exactly_one_receipt_in_order(self):
        self.gateway()
        self.call("shell", {"command": "x"})
        self.call("web_open", {"url": BASE})
        self.call("web_open", {"url": BASE})
        self.call("web_open", {"url": BASE})                                    # third identical → loop guard
        receipts = self.gw.receipts()
        self.assertEqual([r.sequence for r in receipts], [1, 2, 3, 4])
        self.assertEqual([r.status for r in receipts], ["DENIED", "OK", "OK", "DENIED"])
        self.assertEqual(receipts[3].reason_code, "REPEATED_ACTION")


del _Harness

if __name__ == "__main__":
    unittest.main()
