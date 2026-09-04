"""Turn the pair query's user ids into the names the picker shows.

The names are NOT in the database — app.display_name() derives them from
(user_id, gender) at render time with a seeded RNG, so the only way to get
them is to run the same derivation. This is that derivation, kept
deliberately identical to app.py's.

USAGE
=====
Ids straight on the command line:

    python names.py u_0002 u_0164
    python names.py u_0002 male u_0164 female

A saved psql table:

    python names.py rows.txt

Or pasted in (Ctrl+Z then Enter on Windows, Ctrl+D elsewhere):

    python names.py

The query must include the gender columns — a name cannot be derived
without one. Change the pair query's SELECT line to:

    SELECT a.id AS user_a, a.g AS a_gender,
           b.id AS user_b, b.g AS b_gender, a.city
"""

from __future__ import annotations

import random
import re
import sys

# Copied verbatim from app.py. If those lists ever change there, the names
# here drift silently — they are presentation-only, so nothing breaks, but
# the two must be edited together.
FIRST_NAMES = {
    "female": ["Priya", "Ananya", "Meera", "Kavya", "Isha", "Riya", "Sneha", "Tara", "Divya", "Neha", "Pooja", "Simran"],
    "male": ["Arjun", "Rohan", "Vikram", "Aditya", "Karan", "Rahul", "Aryan", "Dev", "Nikhil", "Siddharth", "Varun", "Ishaan"],
}
LAST_NAMES = ["Sharma", "Mehta", "Iyer", "Rao", "Kapoor", "Nair", "Reddy", "Bhatt", "Chopra", "Menon", "Gupta", "Desai"]

ID = re.compile(r"^(?:u_\d+|su_[0-9a-f]+|dp_\S+)$")
GENDER = {"male", "female"}


def display_name(user_id: str, gender: str) -> str:
    rng = random.Random(user_id)
    first = rng.choice(FIRST_NAMES.get(gender, FIRST_NAMES["female"]))
    last = rng.choice(LAST_NAMES)
    return f"{first} {last}"


def parse(text: str) -> list[list[str]]:
    """Pull id/gender/city cells out of pasted psql output.

    Positional parsing would break the moment a column is added or
    reordered, so each cell is classified by what it looks like instead —
    an id, a gender, or neither. Header and rule lines fall out on their
    own because they contain no ids."""
    rows = []
    for line in text.splitlines():
        if "|" not in line or set(line.strip()) <= set("-+| "):
            continue
        cells = [c.strip() for c in line.split("|")]
        if not any(ID.match(c) for c in cells):
            continue
        rows.append(cells)
    return rows


def pairs_from(cells: list[str]) -> tuple[list[tuple[str, str]], str]:
    """Walk the row left to right pairing each id with the gender that
    follows it. A gender that is missing reads as unknown rather than
    guessing, because a wrong name sends someone hunting the picker for a
    person who is not there."""
    people, pending = [], None
    city = ""
    for cell in cells:
        if ID.match(cell):
            if pending is not None:
                people.append((pending, ""))
            pending = cell
        elif cell.lower() in GENDER and pending is not None:
            people.append((pending, cell.lower()))
            pending = None
        elif cell and not ID.match(cell) and cell.lower() not in GENDER:
            if cell.isalpha():
                city = cell
    if pending is not None:
        people.append((pending, ""))
    return people, city


def main() -> int:
    args = sys.argv[1:]

    # Ids straight on the command line — the obvious thing to type, so it
    # has to work rather than trying to open "u_0002" as a file.
    if args and all(ID.match(a) or a.lower() in GENDER for a in args):
        text = " | ".join(args)
    elif args:
        try:
            text = open(args[0], encoding="utf-8").read()
        except FileNotFoundError:
            print(f"No such file: {args[0]}\n\n"
                  "Pass user ids instead:   python names.py u_0002 u_0164\n"
                  "or a saved psql table:   python names.py rows.txt")
            return 1
    else:
        print("Paste the psql rows, then Ctrl+Z + Enter (Windows) "
              "or Ctrl+D (Mac/Linux):\n", file=sys.stderr)
        text = sys.stdin.read()

    rows = parse(text)
    if not rows:
        print("No user ids found in that input.")
        return 1

    print()
    for cells in rows:
        people, city = pairs_from(cells)
        parts = []
        for uid, gender in people:
            if gender:
                parts.append(f"{display_name(uid, gender)} ({uid}, {gender[0].upper()})")
            else:
                # No gender column: show both, rather than pick wrong.
                m, f = display_name(uid, "male"), display_name(uid, "female")
                parts.append(f"{uid}: {m} if male / {f} if female")
        joined = "   +   ".join(parts)
        print(f"{joined}{'   —   ' + city if city else ''}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
