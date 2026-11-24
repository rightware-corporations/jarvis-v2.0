"""F01-A mechanism tests (UNIT): exchange-rate tool + integrity check on FICTIONAL fixtures and on the stored real
bulletin when present. Not evidence about any model."""
import unittest
from pathlib import Path

from labs.f01.bm_fx import ExchangeRateTool, parse_index, pt_number
from labs.f01.integrity import check, value_of
from labs.f01.offline import fixture_source, replay_source

FX = Path("labs/f01/fixtures")
IDX = "https://banco.f01.example/indice/"


def tool(today="2031-03-10"):
    return ExchangeRateTool(fixture_source(FX), today=today, index_url=IDX)


class Parsing(unittest.TestCase):
    def test_numbers_and_index(self):
        self.assertEqual(pt_number("1.078,50"), 1078.5)
        self.assertEqual(pt_number("63,27"), 63.27)
        self.assertEqual(value_of("6.454,00"), 6454.0)
        self.assertEqual(value_of("6454"), 6454.0)
        idx = parse_index((FX / "indice.html").read_text(), IDX)
        self.assertEqual([x["date"] for x in idx], ["2031-03-10", "2031-03-09", "2031-03-06", "2031-02-01"])  # report ignored


class Tool(unittest.TestCase):
    def test_latest_units_thousands_and_unknown_currency(self):
        t = tool()
        r = t("USD", "MZN")
        self.assertEqual((r["status"], r["reference_date"], r["buy"], r["sell"], r["mid"]), ("OK", "2031-03-10", 71.02, 72.44, 71.73))
        self.assertEqual(r["provenance"]["signature"], {"place": "Beira", "date": "2031-03-11"})   # not a publication date
        self.assertEqual(t("JPY", "MZN")["unit"], "MZN por 1000 JPY")
        self.assertEqual(t("EUR", "MZN")["mid"], 1089.3)
        self.assertIn("moeda sem código ISO conhecido: Atlântida / Dracma", r["parse_issues"])
        self.assertEqual(t("XAU", "MZN")["status"], "UNSUPPORTED")

    def test_dates_ambiguity_staleness_and_derivations(self):
        t = tool()
        self.assertEqual(t("USD", "MZN", "2031-03-09")["status"], "AMBIGUOUS")       # duplicated row: never guessed
        r = t("USD", "MZN", "2031-03-06")
        self.assertEqual(r["reference_date"], "2031-03-05")                            # as printed in the document
        self.assertIn("data no documento difere da data do índice", r["parse_issues"])
        self.assertEqual(t("USD", "MZN", "2031-03-08")["status"], "NOT_LISTED")
        self.assertIn("STALE", t("USD", "MZN", "2031-02-01").get("status_note", ""))
        inv = t("MZN", "USD")
        self.assertEqual(inv["status"], "DERIVED")
        self.assertAlmostEqual(inv["inverse"]["value"], 1 / 71.73, places=6)
        cross = t("EUR", "USD")
        self.assertEqual(cross["status"], "DERIVED")
        self.assertIn("÷", cross["derivation"])


class Instruments(unittest.TestCase):
    def test_ecb_route_and_fallback(self):
        t = ExchangeRateTool(fixture_source(FX), today="2031-03-10", index_url=IDX, ecb=fixture_source(FX))
        r = t("EUR", "USD")
        self.assertEqual((r["status"], r["value"], r["reference_date"]), ("OK", 1.0421, "2031-03-07"))
        self.assertIn("Banco Central Europeu", r["rate_type"])
        self.assertEqual(t("GBP", "USD")["status"], "UNSUPPORTED")       # ECB not retrieved → BM has no GBP row
        self.assertEqual(tool()("EUR", "USD")["status"], "DERIVED")      # no ECB source → BM cross, labelled


class Integrity(unittest.TestCase):
    def setUp(self):
        self.t = tool()
        self.r = [self.t("USD", "MZN")]

    def test_sustained_and_derived(self):
        a = "Segundo o Banco, em 10 de março de 2031 o dólar: compra 71,02 MT, venda 72,44 MT, média 71,73 MT. Diferença: 1,42 MT."
        self.assertEqual(check(a, self.r)["verdict"], "PASS")
        self.assertEqual(check("Para 100 dólares à taxa de venda precisa de 7.244,00 MT.", self.r, "quanto custam 100 dólares?")["verdict"], "PASS")

    def test_invented_wrong_attribute_wrong_date_no_record(self):
        self.assertEqual(check("A taxa do dólar é 64,73 MT.", self.r)["issues"][0]["problem"], "UNSUSTAINED")
        self.assertEqual(check("A taxa de compra do dólar é 72,44 MT.", self.r)["issues"][0]["problem"],
                         "WRONG_ATTRIBUTE_OR_CURRENCY")
        self.assertEqual(check("O rand está a 71,73 MT.", self.r)["issues"][0]["problem"], "WRONG_ATTRIBUTE_OR_CURRENCY")
        self.assertIn("WRONG_DATE", [i["problem"] for i in check("Dados de 28 de janeiro de 2025: média 71,73.", self.r)["issues"]])
        self.assertEqual(check("A taxa é 63,91 MT.", [])["verdict"], "FAIL")


@unittest.skipUnless(Path(".runtime/op01-fx/requests.jsonl").is_file(), "offline replay corpus not present")
class RealBulletinOffline(unittest.TestCase):
    def test_parses_every_row_of_the_collected_bulletin(self):
        t = ExchangeRateTool(replay_source(), today="2026-11-24")
        r = t("USD", "MZN")
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["parse_issues"], [])
        codes = ["ZAR", "BWP", "SZL", "MUR", "ZMW", "JPY", "MWK", "TZS", "ZWG", "BRL", "CAD", "CNH", "CNY", "DKK", "GBP",
                 "NOK", "SEK", "CHF", "EUR"]
        self.assertTrue(all(t(c, "MZN")["status"] == "OK" for c in codes))
        self.assertEqual(t("USD", "MZN", "2026-11-20")["status"], "NOT_RETRIEVED")   # listed, not collected offline


if __name__ == "__main__":
    unittest.main()
