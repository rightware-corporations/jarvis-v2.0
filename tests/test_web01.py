"""WEB-01 W0–W2: egress policy, fixture research tools with receipts, verifier, supervised mission.
All offline: the fixture transport is in-process and every "public-mode" test injects an httpx MockTransport.
No test opens a socket (asserted). This is NOT evidence of real Internet research (W3 is not authorised)."""
import copy
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
try:
    import httpx
    from rightware.agent import web as W
    from rightware.web01 import egress as E
    from rightware.web01 import fixture as FX
    from rightware.web01 import research as R
    from rightware.web01.mission import ResearchMission
    from rightware import control_plane as CP
except ImportError:
    httpx = None

POLICY = json.loads((ROOT / "configs/web01/egress.json").read_text()) if (ROOT / "configs/web01/egress.json").is_file() else {}


def no_sockets(test):
    """Any real socket connection during the test is a failure."""
    def boom(*a, **k):
        raise AssertionError("WEB-01 W0–W2 must never open a network connection")
    return mock.patch.object(socket.socket, "connect", boom)(mock.patch.object(socket, "create_connection", boom)(test))


def policy(**over):
    d = copy.deepcopy(POLICY)
    d.update(over)
    return E.EgressPolicy.from_dict(d)


def public_policy(**over):
    d = copy.deepcopy(POLICY)
    d.update(mode="public", allowed_hosts=["pt.example.org", "docs.example.org"])
    d.update(over)
    return E.EgressPolicy.from_dict(d)


class CountingFetcher:
    def __init__(self, inner=None):
        self.inner, self.calls = inner, []

    def fetch(self, url, host_allowed=None, **kw):
        self.calls.append(url)
        return self.inner.fetch(url, host_allowed, **kw)


@unittest.skipIf(httpx is None, "pinned OpenJarvis venv required")
class W0Policy(unittest.TestCase):
    def test_shipped_policy_is_fixture_without_network(self):
        p = E.EgressPolicy.load()
        self.assertEqual((p.mode, p.network_enabled, p.authorization_ref), ("fixture", False, None))
        self.assertTrue(all(h.endswith(".fixture.example") for h in p.allowed_hosts))
        self.assertEqual(p.methods, ("GET",))

    def test_invalid_policies_fail_closed(self):
        bad = [dict(extra=1), dict(methods=["GET", "POST"]), dict(methods=["HEAD"]), dict(allowed_hosts=["*.fixture.example"]),
               dict(allowed_hosts=["Enciclopedia.fixture.example"]), dict(allowed_hosts=["x.fixture.example:8080"]),
               dict(allowed_hosts=[]), dict(network_enabled=True), dict(authorization_ref="op-1"),
               dict(allowed_hosts=["pt.wikipedia.org"]), dict(max_bytes_per_response=W.MAX_BYTES + 1),
               dict(max_redirects=True), dict(timeout_s=0), dict(version="v0"), dict(mode="tunnel")]
        for over in bad:
            d = copy.deepcopy(POLICY)
            d.update(over)
            with self.subTest(over=over), self.assertRaises(E.PolicyError):
                E.EgressPolicy.from_dict(d)
        d = copy.deepcopy(POLICY)
        del d["timeout_s"]
        with self.assertRaises(E.PolicyError):
            E.EgressPolicy.from_dict(d)
        with self.assertRaises(E.PolicyError):
            public_policy(network_enabled=True, authorization_ref="  ")
        with self.assertRaises(E.PolicyError):
            public_policy(allowed_hosts=["a.fixture.example"])

    def test_public_egress_cannot_be_built_without_w3_authorisation(self):
        for p in (public_policy(), public_policy(network_enabled=True, authorization_ref="OP-AUT-1")):
            with self.assertRaises(E.NetworkNotAuthorised):
                E.build_fetcher(p)                         # the default path never passes allow_public
            with self.assertRaises(E.NetworkNotAuthorised):
                E.EgressGuard(p)
        with self.assertRaises(E.NetworkNotAuthorised):
            E.build_fetcher(public_policy(), allow_public=True)     # flag alone is not enough
        with self.assertRaises((E.NetworkNotAuthorised, NotImplementedError)):
            ResearchMission(public_policy(network_enabled=True, authorization_ref="OP-AUT-1"))

    @no_sockets
    def test_guard_refuses_before_any_fetch(self):
        f = CountingFetcher(FX.fixture_fetcher())
        g = E.EgressGuard(policy(), f)
        for url in ("https://fora.fixture.example/", "https://pt.wikipedia.org/wiki/Maputo", "http://127.0.0.1/",
                    "https://169.254.169.254/latest/meta-data", "file:///etc/passwd", "not a url"):
            with self.subTest(url=url), self.assertRaises(E.EgressRefused):
                g.fetch(url)
        with self.assertRaises(E.EgressRefused):
            g.fetch("https://enciclopedia.fixture.example/wiki/Maputo", method="HEAD")
        self.assertEqual(f.calls, [])
        self.assertTrue(all(a["decision"] == "REFUSED" for a in g.audit))

    @no_sockets
    def test_budgets_and_cancel(self):
        g = E.EgressGuard(policy(max_requests_per_mission=2), FX.fixture_fetcher())
        g.fetch("https://enciclopedia.fixture.example/wiki/Maputo")
        g.fetch("https://enciclopedia.fixture.example/wiki/Maputo")
        with self.assertRaisesRegex(E.EgressRefused, "pedidos"):
            g.fetch("https://enciclopedia.fixture.example/wiki/Maputo")
        g = E.EgressGuard(policy(max_total_bytes_per_mission=600), FX.fixture_fetcher())
        p1 = g.fetch("https://enciclopedia.fixture.example/wiki/Mocambique")
        self.assertLessEqual(len(p1.raw), 600)
        with self.assertRaisesRegex(E.EgressRefused, "bytes"):
            g.fetch("https://enciclopedia.fixture.example/wiki/Maputo")
        t = [0.0]
        g = E.EgressGuard(policy(max_seconds_per_mission=5), FX.fixture_fetcher(), clock=lambda: t[0])
        t[0] = 6.0
        with self.assertRaisesRegex(E.EgressRefused, "tempo"):
            g.fetch("https://enciclopedia.fixture.example/wiki/Maputo")
        ev = threading.Event()
        ev.set()
        with self.assertRaisesRegex(E.EgressRefused, "cancelada"):
            E.EgressGuard(policy(), FX.fixture_fetcher(), cancelled=ev).fetch("https://enciclopedia.fixture.example/wiki/Maputo")

    @no_sockets
    def test_per_response_limit_and_redirects(self):
        g = E.EgressGuard(policy(max_bytes_per_response=100), FX.fixture_fetcher())
        p = g.fetch("https://enciclopedia.fixture.example/wiki/Mocambique")
        self.assertEqual((len(p.raw), p.truncated), (100, True))
        g = E.EgressGuard(policy(), FX.fixture_fetcher())
        p = g.fetch("https://enciclopedia.fixture.example/wiki/Capital_de_Mocambique")     # allowed 301
        self.assertEqual(p.final_url, "https://enciclopedia.fixture.example/wiki/Maputo")
        with self.assertRaisesRegex(W.WebRefused, "fora dos sites autorizados"):            # 302 off the allowlist
            g.fetch("https://forum.fixture.example/sair?para=fora")
        g = E.EgressGuard(policy(max_redirects=0), FX.fixture_fetcher())
        with self.assertRaises(W.WebRefused):
            g.fetch("https://enciclopedia.fixture.example/wiki/Capital_de_Mocambique")

    @no_sockets
    def test_public_mode_guarantees_with_injected_transport(self):
        """The W3 path keeps HttpxFetcher's SSRF, DNS and redirect guarantees under the egress allowlist."""
        def handler(request):
            if request.url.path == "/to-metadata":
                return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
            if request.url.path == "/to-other":
                return httpx.Response(302, headers={"location": "https://evil.example.net/"})
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>ok</p>")
        good = lambda host: ["93.184.216.34"]
        mk = lambda resolver, peer=lambda r: True: W.HttpxFetcher(resolver=resolver, transport=httpx.MockTransport(handler),
                                                                  peer_check=peer, ssrf=lambda u: None)
        p = public_policy()
        self.assertEqual(E.EgressGuard(p, mk(good)).fetch("https://pt.example.org/").status, 200)
        with self.assertRaisesRegex(W.WebRefused, "privado"):                     # DNS → private address
            E.EgressGuard(p, mk(lambda h: ["10.0.0.7"])).fetch("https://pt.example.org/")
        with self.assertRaisesRegex(W.WebRefused, "privado"):                     # rebinding-style mixed answer
            E.EgressGuard(p, mk(lambda h: ["93.184.216.34", "127.0.0.1"])).fetch("https://pt.example.org/")
        with self.assertRaises(W.WebRefused):                                     # redirect to metadata IP
            E.EgressGuard(p, mk(good)).fetch("https://pt.example.org/to-metadata")
        with self.assertRaisesRegex(W.WebRefused, "fora dos sites"):              # redirect off the allowlist
            E.EgressGuard(p, mk(good)).fetch("https://pt.example.org/to-other")
        with self.assertRaisesRegex(W.WebRefused, "endereço público"):            # peer re-check after connect
            E.EgressGuard(p, mk(good, peer=lambda r: False)).fetch("https://pt.example.org/")
        with self.assertRaises(W.WebRefused):
            W.validated_addresses("pt.example.org", lambda h: ["93.184.216.34", "192.168.1.1"])


@unittest.skipIf(httpx is None, "pinned OpenJarvis venv required")
class W1ToolsReceiptsVerifier(unittest.TestCase):
    def kit(self, **over):
        p = policy(**over)
        return p, R.ResearchToolkit(E.EgressGuard(p, FX.fixture_fetcher()), FX.search_url)

    @no_sockets
    def test_search_and_open_produce_chained_receipts(self):
        p, kit = self.kit()
        r, results = kit.web_search_public("banco central de Moçambique")
        self.assertEqual(r["status"], "OK")
        self.assertTrue(results and all(u.startswith("https://") and ".fixture.example/" in u for u in results))
        r2, page = kit.web_open_public(results[0])
        r3, _ = kit.web_open_public("https://fora.fixture.example/")
        r4, _ = kit.web_open_public("https://enciclopedia.fixture.example/nao-existe")
        self.assertEqual([x["status"] for x in kit.receipts], ["OK", "OK", "REFUSED", "HTTP_ERROR"])
        self.assertEqual(r3["sha256"], None)
        self.assertEqual(r4["http_status"], 404)
        for a, b in zip(kit.receipts, kit.receipts[1:]):
            self.assertEqual(b["prev"], a["hash"])
        for x in kit.receipts:
            self.assertEqual(R.receipt_hash(x), x["hash"])
            self.assertRegex(x["fetched_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z$")
        self.assertEqual(len(kit.kept[2]), r2["bytes"])

    @no_sockets
    def test_verifier_uses_only_designated_sources(self):
        spec = R.MissionSpec.load()
        p, kit = self.kit()
        kit.web_open_public("https://forum.fixture.example/topico/capital")     # says "Beira" + prompt injection
        v = R.verify(kit.receipts, kit.kept, spec, p.host_allowed)
        self.assertEqual(v["verdict"], "RESEARCH_NOT_VERIFIED")
        self.assertEqual(v["sources"][0]["supports"], [])
        kit.web_open_public("https://estatisticas.fixture.example/paises/mocambique")
        v = R.verify(kit.receipts, kit.kept, spec, p.host_allowed)
        self.assertEqual(dict((o, s) for o, s, _ in v["objectives"]),
                         {"CAPITAL": "VERIFIED", "MOEDA": "VERIFIED", "BANCO_CENTRAL": "NOT_VERIFIED"})
        self.assertEqual(v["verdict"], "RESEARCH_PARTIAL")

    @no_sockets
    def test_tampering_is_detected(self):
        spec = R.MissionSpec.load()
        p, kit = self.kit()
        kit.web_open_public("https://banco-central.fixture.example/sobre")
        kit.web_open_public("https://enciclopedia.fixture.example/wiki/Mocambique")
        self.assertEqual(R.verify(kit.receipts, kit.kept, spec, p.host_allowed)["verdict"], "RESEARCH_VERIFIED")
        kept = dict(kit.kept)
        kept[1] = kept[1].replace(b"Banco de Mo", b"Banco do Mo")
        self.assertEqual(R.verify(kit.receipts, kept, spec, p.host_allowed)["verdict"], "RESEARCH_INVALID_EVIDENCE")
        receipts = copy.deepcopy(kit.receipts)
        receipts[0]["final_url"] = "https://estatisticas.fixture.example/paises/mocambique"
        self.assertEqual(R.verify(receipts, kit.kept, spec, p.host_allowed)["verdict"], "RESEARCH_INVALID_EVIDENCE")
        receipts = copy.deepcopy(kit.receipts[1:])                               # dropped receipt breaks the chain
        self.assertTrue(R.verify(receipts, kit.kept, spec, p.host_allowed)["problems"])

    def test_mission_spec_is_strict(self):
        d = json.loads(R.DEFAULT_MISSION.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            for mutate in (lambda d: d.update(x=1), lambda d: d["objectives"][0].update(sources=[]),
                           lambda d: d.update(max_results_opened_per_search=9), lambda d: d.update(version="v0")):
                bad = copy.deepcopy(d)
                mutate(bad)
                f = Path(tmp) / "m.json"
                f.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    R.MissionSpec.load(f)


@unittest.skipIf(httpx is None, "pinned OpenJarvis venv required")
class W2Mission(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    @no_sockets
    def test_mission_verified_with_sources_and_evidence(self):
        m = ResearchMission(runtime=self.tmp)
        started = []
        o = m.run(threading.Event(), on_start=lambda: started.append(1))
        self.assertEqual((o.state, o.verified, started), (CP.State.RESULTADO_VERIFICADO, True, [1]))
        self.assertEqual(o.operational_state, "RESEARCH_VERIFIED_FIXTURE")
        self.assertEqual({oid for oid, st, _ in o.objectives if st == "VERIFIED"}, {"CAPITAL", "MOEDA", "BANCO_CENTRAL"})
        self.assertTrue(all(s["sha256"] and s["fetched_at"] and s["bytes"] for s in o.sources))
        supported = {x for s in o.sources for x in s["supports"]}
        self.assertEqual(supported, {"CAPITAL", "MOEDA", "BANCO_CENTRAL"})
        self.assertEqual(o.model_commentary_unverified, "")
        self.assertTrue(any("Maputo" in f for f in o.findings))
        files = {p.name for p in m.last_run.iterdir()}
        self.assertEqual(files, {"pages", "receipts.jsonl", "egress_audit.jsonl", "verification.json"})
        receipts = [json.loads(x) for x in (m.last_run / "receipts.jsonl").read_text().splitlines()]
        kept = {int(p.stem): p.read_bytes() for p in (m.last_run / "pages").iterdir()}
        self.assertEqual(R.verify(receipts, kept, m.spec, m.policy.host_allowed)["verdict"], "RESEARCH_VERIFIED")

    @no_sockets
    def test_cancel_stops_mid_mission(self):
        m = ResearchMission(runtime=self.tmp, fetcher_factory=lambda stop: FX.fixture_fetcher(delay=2.0, cancel=stop))
        ev = threading.Event()
        threading.Timer(0.3, m.cancel).start()
        t0 = time.monotonic()
        o = m.run(ev)
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertEqual((o.state, o.verified, o.halt_reason_code), (CP.State.TAREFA_CANCELADA, False, "CANCELLED"))

    @no_sockets
    def test_through_the_control_plane_with_operator_code(self):
        from rightware.console import build
        from tests.test_ui01_gui import TextModel
        entry = build("qwen3.5:2b", TextModel(), 30.0)
        m = ResearchMission(runtime=self.tmp, fetcher_factory=lambda stop: FX.fixture_fetcher(delay=0.2, cancel=stop))
        cp = CP.ControlPlane(entry.text_facade, missions=(m,))
        self.assertIn("pesquisa-publica", cp.capabilities)
        self.assertEqual(cp.authorize_and_run("ABCDEF").reason, "CODE_INVALID")
        state, code = cp.request("pesquisa-publica")
        self.assertEqual(state, CP.State.AUTORIZACAO_NECESSARIA)
        self.assertEqual(cp.authorize_and_run(code.lower()).state, CP.State.RESULTADO_VERIFICADO)
        self.assertIsInstance(cp.authorize_and_run(code), CP.Refusal)          # single use
        _, code = cp.request("pesquisa-publica")
        box = {}
        th = threading.Thread(target=lambda: box.setdefault("o", cp.authorize_and_run(code)))
        th.start()
        time.sleep(0.3)
        self.assertTrue(cp.cancel())
        th.join(5)
        self.assertEqual(box["o"].state, CP.State.TAREFA_CANCELADA)
        with self.assertRaises(ValueError):
            CP.ControlPlane(entry.text_facade, missions=(m, m))

    def test_bridge_exposes_partial_capability_and_sources(self):
        from rightware.gui import bridge as B
        m = ResearchMission(runtime=self.tmp)
        o = m.run(threading.Event())
        d = B.ChatBridge.outcome_dict(o)
        self.assertEqual(d["verified"], True)
        self.assertEqual(len(d["sources"]), len(o.sources))
        self.assertTrue(d["findings"])
        self.assertEqual(B.CAPABILITY_STATUS["pesquisa-publica"][0], "PARCIAL")
        self.assertIn(("internet-publica", "BLOQUEADA"), [(c[0], c[2]) for c in B.PENDING_CAPABILITIES])


if __name__ == "__main__":
    unittest.main()
