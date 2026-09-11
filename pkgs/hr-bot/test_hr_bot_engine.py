"""Unit tests for engine.py — the pure HR-intake logic (no aiogram).

These run fast in the nix flake-check (engine.py imports only stdlib).
The thin FSM handlers in hr_bot.py delegate everything here.
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "engine", str(Path(__file__).parent / "engine.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EngineQuizTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = _load_engine()

    def test_new_state_starts_clean(self):
        st = self.e.new_state("Anna", "anna_u")
        self.assertEqual(st["answers"], {})
        self.assertFalse(st["done"])
        self.assertEqual(st["username"], "anna_u")

    def test_record_answer_roundtrip(self):
        st = self.e.new_state("Anna", "anna_u")
        self.e.record_answer(st, "q1", "Да, подходит")
        self.e.record_answer(st, "q2", "Да, был")
        self.assertTrue(self.e.answers_complete(st))
        self.assertEqual(st["answers"]["q1"], "Да, подходит")

    def test_answers_incomplete_without_both(self):
        st = self.e.new_state("Anna", "")
        self.e.record_answer(st, "q1", "Обсудим")
        self.assertFalse(self.e.answers_complete(st))

    def test_contact_validation_phone(self):
        self.assertTrue(self.e.is_valid_contact("+79990001122"))
        self.assertTrue(self.e.is_valid_contact("+7 (999) 000-11-22"))
        self.assertFalse(self.e.is_valid_contact("123"))
        self.assertFalse(self.e.is_valid_contact(""))

    def test_contact_validation_username(self):
        self.assertTrue(self.e.is_valid_contact("@user_name"))
        self.assertTrue(self.e.is_valid_contact(" @a "))  # stripped, then @
        self.assertFalse(self.e.is_valid_contact("@"))

    def test_make_card_escapes_html(self):
        st = self.e.new_state("<script>Anna</script>", "<i>u</i>")
        self.e.record_answer(st, "q1", "<b>Обсудим</b>")
        self.e.record_answer(st, "q2", "Да")
        self.e.record_answer(st, "q3", "только Telegram")
        card = self.e.make_card(st, 123)
        self.assertNotIn("<script>", card)
        self.assertNotIn("<b>Обсудим</b>", card)

    def test_make_card_phone_line(self):
        st = self.e.new_state("Anna", "u")
        self.e.record_answer(st, "q3", "+79990001122")
        card = self.e.make_card(st, 1)
        self.assertIn("📞 +79990001122", card)

    def test_write_candidate_appends_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "candidates.jsonl")
            st = self.e.new_state("Anna", "u")
            self.e.record_answer(st, "q1", "Обсудим")
            self.e.record_answer(st, "q2", "Да, был")
            self.e.write_candidate(data, st, 42)
            with open(data) as f:
                lines = f.read().splitlines()
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["tg_id"], 42)
            self.assertEqual(rec["answers"]["q1"], "Обсудим")

    def test_append_extra(self):
        st = self.e.new_state("Anna", "u")
        self.e.append_extra(st, "Резюме выше")
        self.e.append_extra(st, "ещё строчка")
        self.assertIn("Резюме выше", st["extra"])

    # ── H1: owner-notice escaping (security) ──
    def test_make_extra_notice_escapes_html(self):
        st = self.e.new_state("<b>Anna</b>", "u")
        self.e.append_extra(st, '<a href="https://evil.tld/?x=1">click</a>')
        text = self.e.make_extra_notice(st, 123)
        self.assertNotIn("<a href", text)
        self.assertNotIn("<b>", text)
        self.assertIn("&lt;a href", text)

    # ── H3: candidates file is written 0600 (PII) ──
    def test_write_candidate_creates_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "candidates.jsonl")
            st = self.e.new_state("Anna", "u")
            self.e.write_candidate(data, st, 42)
            mode = os.stat(data).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    # ── H2/rate-limit: per-user sliding window ──
    def test_rate_limiter_allows_first_and_denies_burst(self):
        rl = self.e.RateLimiter(limit=2, window=60.0)
        now = 1000.0
        self.assertTrue(rl.allow("u1", now))
        self.assertTrue(rl.allow("u1", now + 0.5))
        self.assertFalse(rl.allow("u1", now + 1.0))  # burst denied

    def test_rate_limiter_window_rolls_over(self):
        rl = self.e.RateLimiter(limit=1, window=60.0)
        now = 1000.0
        self.assertTrue(rl.allow("u1", now))
        self.assertFalse(rl.allow("u1", now + 10))
        self.assertTrue(rl.allow("u1", now + 61))  # window closed


if __name__ == "__main__":
    unittest.main(verbosity=2)
