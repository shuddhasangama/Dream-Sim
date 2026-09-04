"""What a city tells us, so sign-up does not have to ask.

Somebody registering in Chennai should not be picking a currency, scrolling
past Punjabi to find Tamil, or being offered a dietary list in the order
that suits Delhi. Every one of those is a question the city already
answers, and each one asked anyway is a reason to abandon the form.

Nothing here is a constraint. These are DEFAULTS and ORDERING only — the
full option list stays available underneath, because a Tamil speaker in
Kolkata is not an error to be corrected. The rule throughout: pre-fill what
is almost certainly right, never remove what might be.

Named locale_defaults rather than locale to stay out of the way of Python's
own `locale` module, which app.py's imports would otherwise shadow.
"""

from __future__ import annotations

from typing import Any

from generate_users import CITIES, DIETS, LANGUAGES_POOL

# ── currency ──────────────────────────────────────────────────────────────
# One entry per country, so adding a city outside India means adding its
# country here rather than editing every band list by hand.

CURRENCIES = {
    "IN": {"code": "INR", "symbol": "₹", "name": "Indian rupee"},
}

# Restaurant budget bands, per currency. The bands ARE the currency —
# "₹ · under 800" means nothing in dollars — so they live together.
BUDGET_BANDS = {
    "INR": [
        "₹ · under 800",
        "₹₹ · 800 – 2,000",
        "₹₹₹ · 2,000 – 4,500",
        "₹₹₹₹ · 4,500+",
    ],
}

# ── the cities themselves ─────────────────────────────────────────────────
# `languages` is the regional shortlist shown first, not a restriction.
# `diets` is the shortlist that leads the dietary options for that city.

CITY_LOCALE: dict[str, dict[str, Any]] = {
    "Mumbai":    {"country": "IN", "languages": ["Marathi", "Hindi", "English", "Gujarati"],
                  "diets": ["Vegetarian", "Everything", "Jain", "Eggetarian"]},
    "Delhi":     {"country": "IN", "languages": ["Hindi", "English", "Punjabi"],
                  "diets": ["Vegetarian", "Everything", "Halal", "No red meat"]},
    "Bangalore": {"country": "IN", "languages": ["Kannada", "English", "Hindi", "Tamil", "Telugu"],
                  "diets": ["Vegetarian", "Everything", "Eggetarian"]},
    "Hyderabad": {"country": "IN", "languages": ["Telugu", "Hindi", "English", "Kannada"],
                  "diets": ["Everything", "Vegetarian", "Halal"]},
    "Pune":      {"country": "IN", "languages": ["Marathi", "Hindi", "English"],
                  "diets": ["Vegetarian", "Everything", "Jain"]},
    "Chennai":   {"country": "IN", "languages": ["Tamil", "English", "Telugu"],
                  "diets": ["Vegetarian", "Everything", "No red meat"]},
    "Kolkata":   {"country": "IN", "languages": ["Bengali", "Hindi", "English"],
                  "diets": ["Everything", "Vegetarian", "No red meat"]},
}

DEFAULT_COUNTRY = "IN"


def _entry(city: str | None) -> dict[str, Any]:
    return CITY_LOCALE.get(city or "", {"country": DEFAULT_COUNTRY, "languages": [], "diets": []})


def country_for(city: str | None) -> str:
    return _entry(city)["country"]


def currency_for(city: str | None) -> dict[str, str]:
    """The currency to price this city's budget bands in."""
    return CURRENCIES[country_for(city)]


def budget_bands_for(city: str | None) -> list[str]:
    return BUDGET_BANDS[currency_for(city)["code"]]


def _shortlist_first(shortlist: list[str], full: list[str]) -> list[str]:
    """The regional options first, in their own order, then everything else
    in the original order. Nothing is dropped — this only changes what a
    person sees without scrolling."""
    seen = [value for value in shortlist if value in full]
    return seen + [value for value in full if value not in seen]


def languages_for(city: str | None) -> list[str]:
    return _shortlist_first(_entry(city)["languages"], LANGUAGES_POOL)


def diets_for(city: str | None) -> list[str]:
    return _shortlist_first(_entry(city)["diets"], DIETS)


def suggested_languages(city: str | None) -> list[str]:
    """Pre-ticked on the form. The regional shortlist, capped at three so
    it reads as a suggestion rather than an assumption about someone."""
    return [lang for lang in _entry(city)["languages"] if lang in LANGUAGES_POOL][:3]


def defaults_for(city: str | None) -> dict[str, Any]:
    """Everything a city implies, in one call for the template."""
    currency = currency_for(city)
    return {
        "city": city,
        "country": country_for(city),
        "currency": currency,
        "budget_bands": budget_bands_for(city),
        "languages": languages_for(city),
        "suggested_languages": suggested_languages(city),
        "diets": diets_for(city),
    }


def known_cities() -> list[str]:
    """Cities with a locale entry, in the generator's own order so the two
    lists cannot silently diverge."""
    return [city for city in CITIES if city in CITY_LOCALE]
