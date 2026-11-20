"""Milestone A1 contract validator: deterministic lab-only tests (no runtime changes)."""
import unittest
from dataclasses import replace

from labs.work07_r3c2.a1_contract_validation import (
    Objective, Preset, PresetRegistry, TEST_REGISTRY, SYNTHETIC_ARCHIVE_PRESET,
    validate_preset,
)

SITES = ("archive.fixture.example",)


def check(preset=SYNTHETIC_ARCHIVE_PRESET, sites=SITES, browse=True):
    return validate_preset(preset, allowed_sites=sites, browse_allowed=browse)


class A1TrustedPresetValidation(unittest.TestCase):
    def test_approved_preset_selected_within_existing_browse_allowlist(self):
        got = TEST_REGISTRY.select("test-archive-two-originals", allowed_sites=SITES, browse_allowed=True)
        self.assertEqual(got, SYNTHETIC_ARCHIVE_PRESET)
        self.assertEqual(len(got.objectives), 2)

    def test_not_browse_enabled_cannot_be_elevated_by_preset(self):
        with self.assertRaises(ValueError):
            check(browse=False)

    def test_host_cannot_expand_session_grants(self):
        with self.assertRaises(ValueError):
            check(sites=("example.com",))

    def test_unknown_preset_cannot_be_selected(self):
        with self.assertRaises(ValueError):
            TEST_REGISTRY.select("model-suggested", allowed_sites=SITES, browse_allowed=True)

    def test_freeform_dict_from_model_never_becomes_a_preset(self):
        with self.assertRaises(ValueError):
            check({"preset_id": "untrusted"})

    def test_duplicate_objective_ids_rejected(self):
        bad = replace(SYNTHETIC_ARCHIVE_PRESET,
                      objectives=(SYNTHETIC_ARCHIVE_PRESET.objectives[0],
                                  SYNTHETIC_ARCHIVE_PRESET.objectives[0]))
        with self.assertRaises(ValueError):
            check(bad)

    def test_empty_objectives_and_all_optional_are_rejected(self):
        for objectives in ((), (replace(SYNTHETIC_ARCHIVE_PRESET.objectives[0], mandatory=False),)):
            with self.subTest(objectives=objectives), self.assertRaises(ValueError):
                check(replace(SYNTHETIC_ARCHIVE_PRESET, objectives=objectives))

    def test_malformed_or_unsupported_schema_and_origin_rejected(self):
        for change in ({"version": "A2"}, {"provenance": "model_generated"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                check(replace(SYNTHETIC_ARCHIVE_PRESET, **change))

    def test_side_effect_verb_is_unsupported(self):
        with self.assertRaises(ValueError):
            check(replace(SYNTHETIC_ARCHIVE_PRESET,
                          objectives=(Objective("SEND", "send_message",
                                                "https://archive.fixture.example/send"),)))

    def test_offsite_http_login_fragment_and_query_rejected(self):
        base = "https://archive.fixture.example/docs/ax-101.html"
        urls = (
            "http://archive.fixture.example/docs/ax-101.html",
            "https://mirror.other.example/docs/ax-101.html",
            "https://person:secret@archive.fixture.example/docs/ax-101.html",
            base + "#page2", base + "?token=secret",
            "https://archive.fixture.example:444/docs/ax-101.html",
            "https://archive.fixture.example/docs/ax-101.html\nX: header",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                check(replace(SYNTHETIC_ARCHIVE_PRESET,
                              objectives=(Objective("BAD", "read_page", url),)))

    def test_unsafe_continuation_limit_rejected(self):
        for limit in (-1, 2, 100):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                check(replace(SYNTHETIC_ARCHIVE_PRESET, max_continuations=limit))

    def test_registry_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            PresetRegistry((SYNTHETIC_ARCHIVE_PRESET, SYNTHETIC_ARCHIVE_PRESET))

    def test_host_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            check(replace(SYNTHETIC_ARCHIVE_PRESET, hosts=(SITES[0], SITES[0])))

    def test_invalid_preset_id_or_type_is_rejected(self):
        for name in ("", "x" * 81):
            with self.subTest(name=name), self.assertRaises(ValueError):
                check(replace(SYNTHETIC_ARCHIVE_PRESET, preset_id=name))

    def test_new_registry_cannot_be_created_from_raw_dicts(self):
        with self.assertRaises(ValueError):
            PresetRegistry(({"preset_id": "model"},))


if __name__ == "__main__":
    unittest.main()
