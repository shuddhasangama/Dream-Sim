"""The rename holds.

2026-09-11, user's rule: "Start calling the app as 'DhaShu' - Dare to
Dream needs to be replaced everywhere."

A rename gets to 95% done and stays there — one screen still saying the
old thing a year later. This is what stops that: the old name anywhere in
the shipped source fails the suite, naming the file.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import brand

ROOT = Path(__file__).parent
SEARCHED = (list(ROOT.glob("*.py")) + list(ROOT.glob("templates/*.html"))
            + list(ROOT.glob("static/*.css")) + list(ROOT.glob("static/*.js")))


class RenameTests(unittest.TestCase):

    def test_the_old_name_appears_nowhere(self):
        offenders = []
        for path in SEARCHED:
            if path.name in ("brand.py", "test_brand.py"):
                continue          # the only two allowed to mention it
            text = path.read_text(encoding="utf-8")
            for retired in brand.RETIRED_NAMES:
                if retired in text:
                    offenders.append(f"{path.name}: {retired!r}")
        self.assertEqual(offenders, [], "the old product name is still in the source")

    def test_there_are_files_to_search(self):
        """A guard that silently searches nothing is worse than none."""
        self.assertGreater(len(SEARCHED), 40)

    def test_the_name_is_what_the_user_asked_for(self):
        self.assertEqual(brand.NAME, "DhaShu")

    def test_the_suffix_helper_reads_right(self):
        self.assertEqual(brand.suffix("REACH"), "REACH — DhaShu")


if __name__ == "__main__":
    unittest.main()
