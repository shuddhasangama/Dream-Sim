"""The product's name, in one place.

2026-09-11, user's rule: "Start calling the app as 'DhaShu' - Dare to
Dream needs to be replaced everywhere."

Why a module rather than 29 edited strings: the name had been typed by
hand into 25 templates and three clause bodies, which is how a rename
gets to 95% done and stays there — one screen still saying the old thing
for a year. Every surface reads NAME now, test_brand.py fails if the old
name reappears anywhere, and a future rename is one line.

The meaning, from the brand note: DhaShu inverts the Sanskrit Shuddha
(शुद्ध), "pure" — purity reached by re-engineering rather than assumed.
Which is the same claim the product makes about trust, so the tagline is
not decoration.
"""

from __future__ import annotations

NAME = "DhaShu"

# Used where a sentence needs to say what the platform IS, not just name
# it — the agreement clauses, mainly, where "DhaShu introduces people"
# has to read as a description of a service.
PLATFORM = "DhaShu"

TAGLINE = "Purity, re-engineered."

# Client answer 8 (2026-11-27): the one support contact, shown wherever the app
# or the web pages offer support, and on the public /delete-account page.
SUPPORT_EMAIL = "hello@dhashu.com"

# The old name, kept ONLY so the test can look for it. Never rendered.
RETIRED_NAMES = ("Dare to Dream", "Dare To Dream", "DARE TO DREAM",
                 "dare-to-dream", "dare to dream")


def suffix(page_title: str) -> str:
    """A browser tab title: 'REACH — DhaShu'."""
    return f"{page_title} — {NAME}"
