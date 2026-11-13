"""WORK-07 Milestone A1 (PRODUCT): trusted opt-in task contracts on AgentSession.

Covers the code-owned catalog, the fail-closed validator, the session entry (default OFF),
no-grant guarantees and A/B compatibility. A1 only stores a validated contract: these tests
also prove it changes no tool call, model call, policy limit, reply or completion. FAKE model
and local fixture only; no Qwen, no network.
"""
import dataclasses
import json
import unittest

from rightware.agent import task_contract as TC

try:
    import httpx  # noqa: F401
    from rightware.agent import session as S
    from labs.work07_r3c1.scenarios import FakeModel, INSTRUCTION, scenario_steps
    from labs.work07_r3c1.site import HOST, START, Archive
except ImportError:              # system Python without the pinned venv
    S = None

PRESET = "synthetic-archive-two-originals"
SITES = ("archive.fixture.example",)
BASE = TC.TRUSTED_PRESETS[PRESET]


def objective(**kw):
    o = BASE.objectives[0]
    return dataclasses.replace(o, **kw)


def contract(**kw):
    return dataclasses.replace(BASE, **kw)


class Catalog(unittest.TestCase):
    def test_catalog_is_code_owned_read_only_and_marks_the_fixture_synthetic(self):
        self.assertEqual(list(TC.TRUSTED_PRESETS), [PRESET])
        self.assertTrue(BASE.synthetic)
        self.assertEqual(BASE.origin, "code_catalog")
        self.assertEqual(BASE.objective_ids, ("AX101", "AX202"))
        self.assertTrue(all(o.identity_rule == "NONE" for o in BASE.objectives))   # no identity proof in A1
        with self.assertRaises(TypeError):
            TC.TRUSTED_PRESETS["evil"] = BASE                                         # mapping proxy
        with self.assertRaises(dataclasses.FrozenInstanceError):
            BASE.objectives = ()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            BASE.objectives[0].url = "https://evil.example/"
        self.assertIsInstance(BASE.objectives, tuple)

    def test_catalog_builder_rejects_invalid_or_duplicate_entries(self):
        with self.assertRaises(TC.TaskContractError):
            TC._build_catalog((BASE, BASE))
        with self.assertRaises(TC.TaskContractError):
            TC._build_catalog((contract(objectives=()),))

    def test_approved_preset_is_selected(self):
        got = TC.select_preset(PRESET, allow={"browse"}, sites=SITES)
        self.assertIs(got, BASE)


class Selection(unittest.TestCase):
    def test_unknown_or_non_string_selections_are_rejected(self):
        for value in ("model-suggested", PRESET.upper(), PRESET + " ", "", json.dumps({"preset_id": PRESET}),
                      {"preset_id": PRESET, "trusted": True}, BASE, contract(preset_id="x"), [PRESET], None, 7):
            with self.subTest(value=str(value)[:40]), self.assertRaises(TC.TaskContractError):
                TC.select_preset(value, allow={"browse"}, sites=SITES)

    def test_a_preset_grants_no_capability_and_no_host(self):
        for allow in (set(), {"web"}, {"actions"}, {"web", "actions"}):
            with self.subTest(allow=allow), self.assertRaises(TC.TaskContractError):
                TC.select_preset(PRESET, allow=allow, sites=SITES)
        for sites in ((), ("example.com",), ("fixture.example",), ("evil.archive.fixture.example",)):
            with self.subTest(sites=sites), self.assertRaises(TC.TaskContractError):
                TC.select_preset(PRESET, allow={"browse"}, sites=sites)
        # session sites written with a trailing dot or upper case still match exactly, no wildcard
        self.assertIs(TC.select_preset(PRESET, allow={"browse"}, sites=("ARCHIVE.fixture.example.",)), BASE)


class Validation(unittest.TestCase):
    def reject(self, c, msg=None):
        with self.assertRaises(TC.TaskContractError, msg=msg):
            TC.validate_contract(c)

    def test_structure_version_origin_and_limits(self):
        for change in ({"schema_version": "A2"}, {"schema_version": "a1"}, {"origin": "approved_preset"},
                       {"origin": "llm"}, {"preset_id": "Bad Id"}, {"preset_id": "x" * 65}, {"preset_id": ""},
                       {"synthetic": "yes"}, {"max_continuations": 2}, {"max_continuations": -1},
                       {"max_continuations": True}, {"hosts": ()}, {"hosts": list(SITES)},
                       {"hosts": SITES * 2}, {"hosts": tuple(f"h{i}.example" for i in range(5))},
                       {"objectives": ()}, {"objectives": list(BASE.objectives)},
                       {"objectives": tuple(objective(oid=f"O{i}", url=f"https://archive.fixture.example/{i}")
                                            for i in range(9))}):
            with self.subTest(change=str(change)[:60]):
                self.reject(contract(**change))

    def test_dicts_subclasses_and_foreign_objects_are_not_contracts(self):
        class Sub(TC.TaskContract):
            pass
        self.reject(dataclasses.asdict(BASE))
        self.reject(Sub(**{f.name: getattr(BASE, f.name) for f in dataclasses.fields(BASE)}))
        self.reject(contract(objectives=({"oid": "AX101", "action": "open_original", "url": BASE.objectives[0].url},)))

    def test_objective_ids_actions_labels_and_identity(self):
        for change in ({"oid": ""}, {"oid": "ax101"}, {"oid": "AX 101"}, {"oid": "A" * 33}, {"oid": 101},
                       {"action": "send_message"}, {"action": "web_open"}, {"action": "click"},
                       {"action": "conditional_open"}, {"label": ""}, {"label": "x" * 121},
                       {"label": "a\nb"}, {"identity_rule": "url_match"}):
            with self.subTest(change=change):
                self.reject(contract(objectives=(objective(**change),)))
        dup_id = (BASE.objectives[0], objective(url="https://archive.fixture.example/docs/other.html"))
        self.reject(contract(objectives=dup_id))
        dup_target = (BASE.objectives[0], objective(oid="AX999"))
        self.reject(contract(objectives=dup_target))

    def test_urls_are_canonical_public_https_on_contract_hosts(self):
        bad_urls = (
            "http://archive.fixture.example/docs/a.html", "ftp://archive.fixture.example/a",
            "javascript:alert(1)", "file:///etc/passwd", "//archive.fixture.example/a",
            "https://user:pw@archive.fixture.example/a", "https://archive.fixture.example@evil.example/a",
            "https://archive.fixture.example/a#frag", "https://archive.fixture.example/a?q=1",
            "https://archive.fixture.example:443/a", "https://archive.fixture.example:8443/a",
            "https://archive.fixture.example:99999/a", "https://archive.fixture.example:abc/a",
            "https://ARCHIVE.fixture.example/a", "https://archive.fixture.example./a",
            "https://evil.example/a", "https://archive.fixture.example.evil.example/a",
            "https://archive.fixture.example", "https://archive.fixture.example/a//b",
            "https://archive.fixture.example/a/../b", "https://archive.fixture.example/./a",
            "https://archive.fixture.example/%2e%2e/a", "https://archive.fixture.example/a%2Fb",
            "https://archive.fixture.example/a%00", "https://archive.fixture.example\\evil.example/a",
            "https://archive.fixture.example/a b", "https://archive.fixture.example/a\tb",
            "https://archívé.fixture.example/a", "https://archive.fixture.example/ä",
            "https://archive.fixture.example/" + "a" * 2048, "", None, 5,
        )
        for url in bad_urls:
            with self.subTest(url=str(url)[:60]):
                self.reject(contract(objectives=(objective(url=url),)))

    def test_hosts_are_canonical_ascii_names(self):
        for host in ("ARCHIVE.fixture.example", "archive.fixture.example.", "localhost", "127.0.0.1",
                     "::1", "[::1]", "xn--", "-bad.example", "bad-.example", "a_b.example", "archívé.example",
                     "a..example", "", 5):
            with self.subTest(host=host):
                self.reject(contract(hosts=(host,)))
        # punycode IDN is an ordinary ASCII name: allowed only if the host itself is listed
        ok = contract(hosts=("xn--archve-gva.example",),
                      objectives=(objective(url="https://xn--archve-gva.example/docs/a.html"),))
        self.assertIs(TC.validate_contract(ok), ok)

    def test_validation_never_raises_anything_but_task_contract_error(self):
        for url in ("https://[::1/a", "https://archive.fixture.example:-1/a", "https://:443/a",
                    "https://archive.fixture.example:/a"):
            with self.subTest(url=url):
                try:
                    TC.validate_contract(contract(objectives=(objective(url=url),)))
                except TC.TaskContractError:
                    pass


@unittest.skipIf(S is None, "pinned OpenJarvis venv required")
class SessionIntegration(unittest.TestCase):
    def session(self, model, **kw):
        archive = Archive()
        kw.setdefault("sites", (HOST,))
        kw.setdefault("allow", {"browse"})
        return S.AgentSession(model, "fake", confirm=lambda q: None, start_url=START,
                              browser_fetcher=archive.fetcher(), budgets=S.Budgets(max_calls=14, deadline_seconds=900),
                              max_turns=14, **kw), archive

    def test_default_off_and_explicit_none_are_identical(self):
        a, _ = self.session(FakeModel([]))
        b, _ = self.session(FakeModel([]), task_preset=None)
        for s in (a, b):
            self.assertIsNone(s.task_contract)
            self.assertIsNone(s.task_contract_status)

    def test_trusted_preset_is_stored_validated_and_not_evaluated(self):
        s, _ = self.session(FakeModel([]), task_preset=PRESET)
        self.assertIs(s.task_contract, BASE)
        self.assertEqual(s.task_contract_status, "NOT_EVALUATED")

    def test_rejections_happen_at_construction_before_any_model_call(self):
        model = FakeModel([])
        for kw in ({"task_preset": "model-json"}, {"task_preset": {"preset_id": PRESET}},
                   {"task_preset": BASE}, {"task_preset": PRESET, "allow": {"web"}},
                   {"task_preset": PRESET, "allow": {"browse"}, "sites": ("other.example",),
                    "start_url": None}):
            with self.subTest(kw=str(kw)[:60]), self.assertRaises(ValueError):
                kw.setdefault("allow", {"browse"})
                start = kw.pop("start_url", START)
                S.AgentSession(model, "fake", confirm=lambda q: None, sites=kw.pop("sites", (HOST,)),
                               start_url=start, browser_fetcher=Archive().fetcher(), **kw)
        self.assertEqual(model.received, [])

    def run_pair(self, name):
        outs = []
        for preset in (None, PRESET):
            model = FakeModel(scenario_steps(name))
            s, archive = self.session(model, task_preset=preset)
            reply = s.run(INSTRUCTION)
            outs.append((s, reply, model, archive))
        return outs

    def test_contract_changes_no_reply_json_completion_calls_or_policy(self):
        for name in ("A_incomplete", "B_complete", "D_refused", "E_premature"):
            with self.subTest(name=name):
                (s0, r0, m0, a0), (s1, r1, m1, a1) = self.run_pair(name)
                self.assertEqual(S.reply_json(r0), S.reply_json(r1))                 # byte-identical JSON
                self.assertEqual((r0.completion, r0.flags, r0.halted, r0.sources, r0.verification),
                                 (r1.completion, r1.flags, r1.halted, r1.sources, r1.verification))
                self.assertEqual(len(m0.received), len(m1.received))                 # no extra model calls
                self.assertEqual([t for t in m0.received[0] if t["role"].lower().endswith("system")],
                                 [t for t in m1.received[0] if t["role"].lower().endswith("system")])
                self.assertEqual(a0.requests, a1.requests)                          # same network requests
                self.assertEqual(s0._policy.per_tool, s1._policy.per_tool)
                self.assertEqual(s0._policy.calls, s1._policy.calls)
                self.assertNotEqual(r1.completion, "COMPLETE_VERIFIED")
                self.assertEqual(s1.task_contract_status, "NOT_EVALUATED")           # still not evaluated

    def test_no_new_tools_quotas_or_reply_fields(self):
        self.assertEqual({n: (t.session_flag, t.max_calls) for n, t in S.TOOLS.items()},
                         {"web_read": ("web", 3), "windows_action": ("actions", 1), "web_open": ("browse", 3),
                          "web_type": ("browse", 4), "web_submit": ("browse", 4), "web_follow": ("browse", 6),
                          "web_find": ("browse", 6)})
        self.assertEqual([f.name for f in dataclasses.fields(S.AgentReply)],
                         ["text", "completion", "outcomes", "sources", "halted", "flags", "verification"])
        self.assertEqual([f.name for f in dataclasses.fields(S.ToolOutcome)], ["tool", "status", "content", "evidence"])
        (_, r0, _, _), (_, r1, _, _) = self.run_pair("A_incomplete")
        self.assertEqual(set(json.loads(S.reply_json(r1))), {"completion", "halted", "flags", "verification",
                                                             "sources", "outcomes"})


if __name__ == "__main__":
    unittest.main()
