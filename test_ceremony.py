"""Tests for ceremony.py — playbook, sign, face, verified (Segment E).

The same four steps run six times across the journey. That is the whole
reason this module exists, so most of what is worth pinning is that the
parameterisation did not quietly become five special cases: every kind
must produce clauses, and the ordering must hold for all of them.

The other half is refusal. A ceremony that can be half-completed and still
look signed is worse than one that cannot be completed at all, so the
skip-ahead cases get more attention here than the happy path.
"""

from __future__ import annotations

import unittest

import ceremony


def fresh(kind=ceremony.DATE_AGREEMENT):
    return ceremony.new_state("u1", kind, "plan-1", "W1 Mon 09:00")


def sign(state, name="Asha Rao", at="W1 Mon 09:05", acks=None):
    """Sign with every term ticked. Signing is refused without them, so
    the happy path has to say so explicitly."""
    keys = list(ceremony.ack_keys(state["kind"])) if acks is None else acks
    return ceremony.sign(state, name, keys, at)


def completed(kind=ceremony.DATE_AGREEMENT, user_id="u1"):
    s = ceremony.new_state(user_id, kind, "plan-1", "W1 Mon 09:00")
    s = ceremony.ack_playbook(s)
    return ceremony.capture_face(sign(s))


class KindTests(unittest.TestCase):
    def test_all_five_kinds_carry_a_label_scope_and_unlock(self):
        for kind in ceremony.KINDS:
            with self.subTest(kind=kind):
                meta = ceremony.kind_meta(kind)
                for field in ("label", "blurb", "scope", "unlocks"):
                    self.assertTrue(meta[field], f"{kind}.{field}")

    def test_an_unknown_kind_raises_rather_than_rendering_a_blank_agreement(self):
        with self.assertRaises(ValueError):
            ceremony.kind_meta("marriage_contract")

    def test_only_the_two_paid_occasions_carry_a_fee(self):
        charged = sorted(k for k, m in ceremony.KINDS.items() if m["fee"])
        self.assertEqual(charged, [ceremony.DATE_AGREEMENT, ceremony.STAGE_GATE])

    def test_no_kind_uses_the_forbidden_word(self):
        """docs/CLAUDE.md: never "contract" in identifiers or copy."""
        for kind, meta in ceremony.KINDS.items():
            with self.subTest(kind=kind):
                blob = " ".join([kind, meta["label"], meta["blurb"], meta["unlocks"]]).lower()
                self.assertNotIn("contract", blob)


class StepOrderTests(unittest.TestCase):
    def test_a_new_ceremony_starts_at_the_playbook(self):
        self.assertEqual(ceremony.next_step(fresh()), ceremony.PLAYBOOK)

    def test_the_four_steps_run_in_order(self):
        s = fresh()
        seen = [ceremony.next_step(s)]
        s = ceremony.ack_playbook(s)
        seen.append(ceremony.next_step(s))
        s = sign(s)
        seen.append(ceremony.next_step(s))
        s = ceremony.capture_face(s)
        seen.append(ceremony.next_step(s))
        self.assertEqual(seen, [ceremony.PLAYBOOK, ceremony.SIGN, ceremony.FACE, ceremony.DONE])

    def test_you_cannot_sign_a_playbook_you_have_not_opened(self):
        s = sign(fresh())
        self.assertIsNone(s["signed_name"])
        self.assertEqual(ceremony.next_step(s), ceremony.PLAYBOOK)

    def test_the_face_step_will_not_run_before_a_signature(self):
        s = ceremony.capture_face(ceremony.ack_playbook(fresh()))
        self.assertFalse(s["face_verified"])
        self.assertEqual(ceremony.next_step(s), ceremony.SIGN)

    def test_a_blank_signature_is_refused_rather_than_stored_empty(self):
        s = ceremony.ack_playbook(fresh())
        for blank in ("", "   ", None):
            with self.subTest(value=blank):
                self.assertIsNone(sign(s, name=blank)["signed_name"])

    def test_a_signature_is_trimmed(self):
        s = sign(ceremony.ack_playbook(fresh()), name="  Asha Rao  ")
        self.assertEqual(s["signed_name"], "Asha Rao")

    def test_rows_read_back_as_booleans_behave_the_same_as_zero_and_one(self):
        """SQLite hands these back as 0/1 and psycopg as True/False. The
        step machine must not read one as further along than the other."""
        as_ints = {**fresh(), "playbook_ack": 1, "signed_name": "Asha Rao", "face_verified": 1}
        as_bools = {**fresh(), "playbook_ack": True, "signed_name": "Asha Rao", "face_verified": True}
        self.assertEqual(ceremony.next_step(as_ints), ceremony.next_step(as_bools))


class ProgressTests(unittest.TestCase):
    def test_the_rail_marks_exactly_one_step_current(self):
        for state in (fresh(), ceremony.ack_playbook(fresh()), completed()):
            with self.subTest(step=ceremony.next_step(state)):
                current = [s for s in ceremony.progress(state) if s["state"] == "current"]
                self.assertEqual(len(current), 1)

    def test_everything_before_the_current_step_reads_as_done(self):
        rail = ceremony.progress(sign(ceremony.ack_playbook(fresh()), name="A", at="t"))
        self.assertEqual([s["state"] for s in rail], ["done", "done", "current", "todo"])


class CompletionTests(unittest.TestCase):
    def test_completing_stamps_the_time_once_and_does_not_move_it(self):
        s = ceremony.complete(completed(), "W1 Mon 10:00")
        self.assertEqual(s["completed_at"], "W1 Mon 10:00")
        self.assertEqual(ceremony.complete(s, "W1 Tue 10:00")["completed_at"], "W1 Mon 10:00")

    def test_an_unfinished_ceremony_cannot_be_stamped_complete(self):
        s = ceremony.complete(ceremony.ack_playbook(fresh()), "W1 Mon 10:00")
        self.assertIsNone(s["completed_at"])

    def test_one_signature_is_half_of_one(self):
        """A ceremony binds two people. Nothing takes effect on one."""
        mine = completed(user_id="u1")
        self.assertFalse(ceremony.both_complete([mine], "u1", "u2"))
        self.assertTrue(ceremony.both_complete([mine, completed(user_id="u2")], "u1", "u2"))

    def test_a_partner_who_started_but_did_not_finish_does_not_count(self):
        half = ceremony.ack_playbook(ceremony.new_state("u2", ceremony.DATE_AGREEMENT, "plan-1", "t"))
        self.assertFalse(ceremony.both_complete([completed("date_agreement", "u1"), half], "u1", "u2"))


class TermTests(unittest.TestCase):
    """The terms are what a signature actually agrees to. Ticking them on
    someone's behalf — which the date flow used to do — records consent
    that was never given, so every refusal here matters more than the
    happy path does."""

    def test_every_kind_spells_its_terms_out(self):
        for kind in ceremony.KINDS:
            with self.subTest(kind=kind):
                acks = ceremony.acks_for(kind)
                self.assertGreaterEqual(len(acks), 3)
                for ack in acks:
                    self.assertTrue(ack["key"] and ack["label"])
                    self.assertGreater(len(ack["term"]), 40, "a term has to say something")

    def test_the_date_terms_are_exactly_the_signature_row_fields(self):
        """The date ceremony is mirrored into a Signature row field by
        field. Drift between these two lists silently stops recording
        consent, and nothing would fail at the time."""
        import dateplan
        self.assertEqual(tuple(ceremony.ack_keys(ceremony.DATE_AGREEMENT)), dateplan.ACK_FIELDS)

    def test_no_term_key_is_reused_across_kinds_with_different_wording(self):
        wording = {}
        for kind in ceremony.KINDS:
            for ack in ceremony.acks_for(kind):
                if ack["key"] in wording:
                    self.assertEqual(wording[ack["key"]], ack["term"], ack["key"])
                wording[ack["key"]] = ack["term"]

    def test_signing_without_the_terms_is_refused(self):
        s = ceremony.ack_playbook(fresh())
        self.assertIsNone(sign(s, acks=[])["signed_name"])

    def test_signing_with_one_term_missing_is_refused(self):
        s = ceremony.ack_playbook(fresh())
        keys = list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))
        for i in range(len(keys)):
            with self.subTest(missing=keys[i]):
                partial = keys[:i] + keys[i + 1:]
                self.assertIsNone(sign(s, acks=partial)["signed_name"])

    def test_a_signature_records_which_terms_were_ticked(self):
        s = sign(ceremony.ack_playbook(fresh()))
        self.assertEqual(sorted(ceremony.signed_acks(s)),
                         sorted(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))

    def test_terms_that_are_not_this_kinds_are_ignored_rather_than_counted(self):
        """A tick for a term this ceremony never showed cannot stand in for
        one it did."""
        s = ceremony.ack_playbook(fresh())
        keys = list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))
        self.assertIsNone(sign(s, acks=keys[:-1] + ["ack_invented"])["signed_name"])

    def test_missing_acks_lists_what_is_outstanding(self):
        s = ceremony.ack_playbook(fresh())
        self.assertEqual(ceremony.missing_acks(s), list(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))
        self.assertEqual(ceremony.missing_acks(s, list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))), [])

    def test_stored_acks_survive_a_row_read_back_as_text(self):
        """SQLite and psycopg both hand this back as a JSON string."""
        s = {**fresh(), "acks_json": '["ack_conduct", "ack_liability"]'}
        self.assertEqual(ceremony.signed_acks(s), ["ack_conduct", "ack_liability"])

    def test_a_corrupt_acks_column_reads_as_nothing_ticked(self):
        for bad in ("", "not json", "{}", None):
            with self.subTest(value=bad):
                self.assertEqual(ceremony.signed_acks({**fresh(), "acks_json": bad}), [])


class ClauseTests(unittest.TestCase):
    def test_every_kind_produces_numbered_clauses(self):
        for kind in ceremony.KINDS:
            with self.subTest(kind=kind):
                clauses = ceremony.clauses_for(kind)
                self.assertGreaterEqual(len(clauses), 4)
                self.assertEqual([c["n"] for c in clauses],
                                 [str(i + 1) for i in range(len(clauses))])
                for c in clauses:
                    self.assertTrue(c["title"] and c["body"])

    def test_the_date_agreement_reads_back_what_both_people_already_said(self):
        clauses = ceremony.date_clauses({
            "slot": "W2 Sat 19:30", "meal": "Dinner", "cuisine": "Thai",
            "budget": "₹1500–2500", "bill_split": "Pay your own",
            "my_diet": "vegetarian", "their_diet": "eats everything",
        })
        blob = " ".join(c["body"] for c in clauses)
        for value in ("W2 Sat 19:30", "Thai", "₹1500–2500", "Pay your own",
                      "vegetarian", "eats everything"):
            self.assertIn(value, blob)

    def test_a_missing_value_degrades_to_words_rather_than_rendering_none(self):
        """An agreement with "None" in a clause is not one anyone should
        be asked to sign."""
        for c in ceremony.date_clauses({}):
            self.assertNotIn("None", c["body"])

    def test_a_recorded_greeting_leads_the_courtesies_clause(self):
        with_greeting = ceremony.date_clauses({"greeting": "no-contact"})
        without = ceremony.date_clauses({})
        courtesies = next(c for c in with_greeting if c["title"] == "Courtesies")
        self.assertIn("no contact", courtesies["body"])
        self.assertNotIn("no contact", next(c for c in without if c["title"] == "Courtesies")["body"])

    def test_the_relationship_entry_says_what_it_is_not(self):
        blob = " ".join(c["body"] for c in ceremony.clauses_for(ceremony.RELATIONSHIP_ENTRY)).lower()
        self.assertIn("not", blob)
        self.assertIn("legal", blob)

    def test_the_stage_checkpoint_names_the_stage_being_entered(self):
        clauses = ceremony.clauses_for(ceremony.STAGE_GATE, {"next_stage_name": "Engaged"})
        self.assertIn("Engaged", " ".join(c["body"] for c in clauses))


class IdentityTests(unittest.TestCase):
    def test_the_row_id_keeps_recurrences_of_one_kind_apart(self):
        """The same kind happens again for the next date and the next
        stage. If the id collapsed them, signing once would look like
        signing forever."""
        a = ceremony.new_state("u1", ceremony.DATE_AGREEMENT, "plan-1", "t")
        b = ceremony.new_state("u1", ceremony.DATE_AGREEMENT, "plan-2", "t")
        self.assertNotEqual(a["id"], b["id"])

    def test_two_people_at_the_same_ceremony_get_separate_rows(self):
        a = ceremony.new_state("u1", ceremony.DATE_AGREEMENT, "plan-1", "t")
        b = ceremony.new_state("u2", ceremony.DATE_AGREEMENT, "plan-1", "t")
        self.assertNotEqual(a["id"], b["id"])


if __name__ == "__main__":
    unittest.main()
