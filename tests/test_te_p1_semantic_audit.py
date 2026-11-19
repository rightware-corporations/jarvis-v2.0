"""JRV-TE-P1 audit of the value-strict semantic checker (JRV-BP-039). Deterministic, no agents/models.

Positive cases are the REAL reports the candidates wrote (stored in the committed evidence JSON).
Negative cases mutate them value by value. The original strict scorer (score.py) is kept unchanged and
its verdicts on the same reports are asserted, so neither checker silently replaces the other.
"""
import copy
import json
import pathlib
import unittest

from labs.te_p1_bakeoff import score, score_semantic as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/te_p1_live/te_p1_live_evidence_2026-11-18.json"
PRODUCTS = {"AtlasBoard": "atlasboard", "NovaView": "novaview", "TerraLens": "terralens"}
GOOD_EVENTS = [{"path": p, "http_status": c} for p, c in (("/", 200), ("/catalog", 200), ("/vendors/atlasboard", 200),
                                                          ("/vendors/novaview", 200), ("/vendors/terralens", 503),
                                                          ("/vendors/terralens-factsheet", 200))]


def real_reports():
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {k: v["agent_report"] for k, v in data.items() if isinstance(v.get("agent_report"), dict)}


class SemanticPositive(unittest.TestCase):
    def test_every_real_candidate_report_is_judged_by_the_same_function(self):
        reports = real_reports()
        self.assertTrue({"goose-t1-run2", "hermes-t1", "goose-t2"} <= set(reports))
        for name, rep in reports.items():
            with self.subTest(name=name):
                self.assertEqual(S.check(rep)["semantic_gate"], "PASS")

    def test_schema_variants_with_correct_values_pass(self):
        variant = {
            "recomendação": {"nome": "TerraLens"},
            "fontes": ["http://fixture:8765/vendors/terralens-factsheet"],
            "produtos": [
                {"nome": "AtlasBoard", "suporte_mac": "sim", "csv": "sim", "offline": "sim", "agendamento": "não",
                 "preço": "USD 0/mês"},
                {"nome": "NovaView", "suporte_mac": True, "csv": True, "offline": False, "agendamento": True,
                 "preço": 9},
                {"nome": "TerraLens", "suporte_mac": True, "csv": True, "offline": True, "agendamento": True,
                 "preço": "12"},
            ],
        }
        self.assertEqual(S.check(variant)["semantic_gate"], "PASS")


class SemanticNegative(unittest.TestCase):
    def test_every_single_wrong_value_in_a_real_report_fails(self):
        for name, rep in real_reports().items():
            for product, key in PRODUCTS.items():
                for field in ("mac", "csv", "offline", "scheduled", "price"):
                    mutated = copy.deepcopy(rep)
                    changed = _mutate(mutated, product, field)
                    if not changed:
                        continue
                    with self.subTest(report=name, product=product, field=field):
                        self.assertEqual(S.check(mutated)["semantic_gate"], "FAIL")

    def test_wrong_or_missing_recommendation_and_missing_product_or_source_fail(self):
        rep = real_reports()["hermes-t1"]
        cases = []
        r = copy.deepcopy(rep)
        _set_recommendation(r, "NovaView")
        cases.append(("wrong recommendation", r))
        r = copy.deepcopy(rep)
        _drop_recommendation(r)
        cases.append(("no recommendation", r))
        r = json.loads(json.dumps(rep).replace("/vendors/terralens-factsheet", "/vendors/terralens"))
        cases.append(("no factsheet source", r))
        r = json.loads(json.dumps(rep).replace("NovaView", "OtherView"))
        cases.append(("product missing", r))
        for label, case in cases:
            with self.subTest(case=label):
                self.assertEqual(S.check(case)["semantic_gate"], "FAIL")

    def test_contradictory_duplicates_cannot_hide_an_error(self):
        rep = copy.deepcopy(real_reports()["goose-t1-run2"])
        rep["extra_view"] = [{"name": "TerraLens", "offline_mode": False}]      # contradiction elsewhere
        self.assertEqual(S.check(rep)["semantic_gate"], "FAIL")

    def test_not_recommended_key_is_not_a_recommendation(self):
        rep = copy.deepcopy(real_reports()["goose-t1-run2"])
        rep = {"not_recommended": "NovaView", **rep}
        self.assertEqual(S.check(rep)["recommended"], "TerraLens")
        rep2 = {k: v for k, v in rep.items() if not k.lower().startswith("recommend")}
        self.assertNotEqual(S.check(rep2)["semantic_gate"], "PASS")

    def test_non_objects_and_prose_fail(self):
        for bad in (None, [], "TerraLens is best", {"answer": "TerraLens"}):
            with self.subTest(bad=bad):
                self.assertEqual(S.check(bad)["semantic_gate"], "FAIL")


class StrictScorerPreserved(unittest.TestCase):
    def test_original_strict_verdicts_on_real_reports_are_unchanged(self):
        for name, rep in real_reports().items():
            with self.subTest(name=name):
                v = score.score(GOOD_EVENTS, rep)
                self.assertEqual((v["report_matches_synthetic_oracle"], v["http_level_gate"]), (False, "FAIL"))
                self.assertFalse(v["task_accepted"] or v["autonomous_recovery_verified"])

    def test_strict_oracle_report_still_passes_strict_but_not_semantic(self):
        oracle = {"recommendation": "TerraLens", "price_usd_month": 12, "offline": True, "mac": True, "csv": True,
                  "scheduled_automation": True}
        self.assertEqual(score.score(GOOD_EVENTS, oracle)["http_level_gate"], "PASS")
        self.assertEqual(S.check(oracle)["semantic_gate"], "FAIL")     # does not describe all three products


def _product_nodes(obj):
    if isinstance(obj, dict):
        name = next((obj[k] for k in ("name", "product", "product_name", "nome") if isinstance(obj.get(k), str)), None)
        if name in PRODUCTS:
            yield name, obj
        for k, v in obj.items():
            if k in PRODUCTS and isinstance(v, dict):
                yield k, v
            yield from _product_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _product_nodes(v)


def _mutate(rep, product, field):
    pattern = S._FIELD[field]
    for name, node in _product_nodes(rep):
        if name != product:
            continue
        stack = [node]
        while stack:
            d = stack.pop()
            for k, v in list(d.items()):
                if isinstance(v, dict):
                    stack.append(v)
                elif pattern.search(k) and "max" not in k.lower():
                    if field == "price" and S._num(v) is not None:
                        d[k] = S._num(v) + 1
                        return True
                    if field != "price" and S._bool(v) is not None:
                        d[k] = not S._bool(v)
                        return True
    return False


def _set_recommendation(rep, value):
    for k in list(rep):
        if k.lower().startswith(("recommend", "recomend")):
            if isinstance(rep[k], dict):
                for kk in ("product_name", "name", "product", "nome"):
                    if kk in rep[k]:
                        rep[k][kk] = value
                        return
            rep[k] = value
            return


def _drop_recommendation(rep):
    for k in [k for k in rep if k.lower().startswith(("recommend", "recomend"))]:
        del rep[k]




class FieldMatching(unittest.TestCase):
    def test_mac_field_does_not_match_inside_automacoes(self):
        rep = {"recomendacao": "TerraLens", "fontes": ["https://x/vendors/terralens-factsheet"], "comparacao": [
            {"produto": "AtlasBoard", "suporte_mac": True, "csv": True, "offline": True, "automacoes_agendadas": False,
             "preco_usd_mes": 0},
            {"produto": "NovaView", "suporte_mac": True, "csv": True, "offline": False, "automacoes_agendadas": True,
             "preco_usd_mes": 9},
            {"produto": "TerraLens", "suporte_mac": True, "csv": True, "offline": True, "automacoes_agendadas": True,
             "preco_usd_mes": 12}]}
        self.assertEqual(S.check(rep)["semantic_gate"], "PASS")
        rep["comparacao"][0]["suporte_mac"] = False                         # a genuinely wrong Mac value still fails
        self.assertEqual(S.check(rep)["semantic_gate"], "FAIL")
        for key in ("mac", "Mac_support", "macOS", "suporte_mac"):
            self.assertTrue(S._FIELD["mac"].search(key), key)
        for key in ("automacoes", "automações_agendadas", "Automação"):
            self.assertFalse(S._FIELD["mac"].search(key), key)


class ReportExtraction(unittest.TestCase):
    def test_last_json_object_returns_the_outermost_report_not_a_nested_part(self):
        from labs.te_p1_bakeoff.live_harness import last_json_object
        text = ('intro {"a": 1} texto\n```json\n{"relatorio": {"produtos": [{"nome": "X"}], '
                '"recomendacao": {"produto": "TerraLens"}}, "fontes": ["u"]}\n```\nfim {broken')
        self.assertEqual(list(last_json_object(text)), ["relatorio", "fontes"])
        self.assertEqual(last_json_object('a {"x": {"y": 2}} b {"z": 3}'), {"z": 3})
        self.assertIsNone(last_json_object("sem json"))


if __name__ == "__main__":
    unittest.main()
