-- ═══════════════════════════════════════════════════════════════════════
--  Queries for picking a test pair, and for seeing why one isn't working.
--  Paste into Railway → your Postgres service → Data / Query.
--
--  Why these exist: display names are NOT stored. app.display_name()
--  computes them at render time from random.Random(user_id), so the same
--  id always shows the same name but no query can reproduce one. The id
--  is the only real handle, and only the database knows which ids fit
--  which -- the population was seeded once and the generator has changed
--  since, so regenerating it locally does NOT reproduce what is deployed.
-- ═══════════════════════════════════════════════════════════════════════


-- ── 1. Did the Segment E/F/G deploy land? ─────────────────────────────
-- "Ceremony" is the table Segment E added. init_db() runs on every
-- request, so it appears on the first page load after the deploy -- no
-- migration step.

SELECT tablename FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('Ceremony', 'Match', 'LockIn', 'DatePlan', 'DateOutcome')
ORDER BY tablename;


-- ── 2. What is actually in the pool, and how old is it? ───────────────
-- has_budget / has_cuisine etc. count users carrying the Stats fields
-- added on 2026-09-03. Zeros mean the seeded population predates that
-- change: those users have no budget or cuisine, so the date agreement's
-- readback has nothing to read for them.

SELECT journey_state, bgv_status, count(*) AS users,
       count(*) FILTER (WHERE stats_json::jsonb ? 'budget')          AS has_budget,
       count(*) FILTER (WHERE stats_json::jsonb ? 'cuisine')         AS has_cuisine,
       count(*) FILTER (WHERE stats_json::jsonb ? 'smoking')         AS has_smoking,
       count(*) FILTER (WHERE stats_json::jsonb ? 'fitness_routine') AS has_fitness
FROM "User"
GROUP BY journey_state, bgv_status
ORDER BY journey_state, bgv_status;


-- ── 3. THE ONE YOU WANT: a testable pair ──────────────────────────────
-- Two verified, dating users who fit each other's filters. This mirrors
-- matching.fits_filters() + mutual_open() clause for clause; checked
-- against the Python on a 126-user verified pool, same answer exactly.
--
-- One deliberate narrowing: it only considers SAME-CITY pairs. Every
-- different-city distance in matching.py is >= 120 km and almost nobody's
-- distance_max reaches that, so this returns a strict subset of the real
-- matches -- it can miss a pair, it cannot invent one.

WITH u AS (
  SELECT id,
         stats_json::jsonb       AS s,
         preferences_json::jsonb AS p,
         vision_json::jsonb      AS v,
         stats_json::jsonb->>'city'   AS city,
         stats_json::jsonb->>'gender' AS gender
  FROM "User"
  WHERE bgv_status = 'verified' AND journey_state = 'dating'
),
fits AS (
  SELECT a.id AS a_id, b.id AS b_id
  FROM u a JOIN u b
    ON  a.gender <> b.gender
    AND a.city = b.city
    AND (a.p->'adjustable'->'distance_km'->>0)::numeric <= 0
    -- the four range levers: A's stated range against B's actual stat
    AND (b.s->>'age')::numeric       BETWEEN (a.p->'adjustable'->'age'->>0)::numeric
                                         AND (a.p->'adjustable'->'age'->>1)::numeric
    AND (b.s->>'height_cm')::numeric BETWEEN (a.p->'adjustable'->'height_cm'->>0)::numeric
                                         AND (a.p->'adjustable'->'height_cm'->>1)::numeric
    AND (b.s->>'weight_kg')::numeric BETWEEN (a.p->'adjustable'->'weight_kg'->>0)::numeric
                                         AND (a.p->'adjustable'->'weight_kg'->>1)::numeric
    AND (b.s->>'waist_in')::numeric  BETWEEN (a.p->'adjustable'->'waist_in'->>0)::numeric
                                         AND (a.p->'adjustable'->'waist_in'->>1)::numeric
    -- nationality: 'Any' accepted, or B's nationality named
    AND ( a.p->'adjustable'->'nationality' ? 'Any'
       OR a.p->'adjustable'->'nationality' ? (b.s->>'nationality') )
    -- religion tiers: any / same / related
    AND ( a.p->'adjustable'->'religion' ? 'any'
       OR ( a.p->'adjustable'->'religion' ? 'same'
            AND b.s->>'religion' = a.s->>'religion' )
       OR ( a.p->'adjustable'->'religion' ? 'related'
            AND CASE b.s->>'religion'
                  WHEN 'Hindu' THEN 'dharmic'   WHEN 'Sikh'      THEN 'dharmic'
                  WHEN 'Spiritual' THEN 'dharmic'
                  WHEN 'Muslim' THEN 'abrahamic' WHEN 'Christian' THEN 'abrahamic'
                  WHEN 'None' THEN 'unaffiliated' END
              = CASE a.s->>'religion'
                  WHEN 'Hindu' THEN 'dharmic'   WHEN 'Sikh'      THEN 'dharmic'
                  WHEN 'Spiritual' THEN 'dharmic'
                  WHEN 'Muslim' THEN 'abrahamic' WHEN 'Christian' THEN 'abrahamic'
                  WHEN 'None' THEN 'unaffiliated' END ) )
    -- dealbreakers. non_smoker / non_drinker have backing fields now but
    -- matching.py still treats them as vacuously satisfied, so only these
    -- three actually bite.
    AND ( NOT a.p->'fixed'->'dealbreakers' ? 'veg_only'
          OR b.s->>'diet' IN ('Vegetarian','Vegan','Jain') )
    AND ( NOT a.p->'fixed'->'dealbreakers' ? 'wants_kids'
          OR     EXISTS (SELECT 1 FROM jsonb_array_elements(b.v) k WHERE k->>'key' = 'Kids') )
    AND ( NOT a.p->'fixed'->'dealbreakers' ? 'no_kids_wanted'
          OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(b.v) k WHERE k->>'key' = 'Kids') )
)
SELECT f.a_id, f.b_id, a.city,
       a.s->>'age' AS a_age, a.gender AS a_gender, a.s->>'diet' AS a_diet,
       b.s->>'age' AS b_age, b.gender AS b_gender, b.s->>'diet' AS b_diet
FROM fits f
JOIN fits r ON r.a_id = f.b_id AND r.b_id = f.a_id     -- mutual, both ways
JOIN u a ON a.id = f.a_id
JOIN u b ON b.id = f.b_id
WHERE f.a_id < f.b_id
ORDER BY f.a_id
LIMIT 20;


-- ── 4. The week-1 match table ─────────────────────────────────────────
-- Yes, "Match" is the table -- {user_id, candidate_id, week, slot,
-- revealed_at, window_closes_at, action, pass_reason}.
--
-- IMPORTANT: rows are generated LAZILY. app._get_or_generate_matches()
-- writes them the first time a user opens /week, and only then. Empty
-- result = nobody has opened their week yet, not "no matches exist".
-- Lock-in needs a RECIPROCAL row (both directions) with action='interest'.

SELECT m.user_id, m.candidate_id, m.slot, m.action,
       (r.id IS NOT NULL) AS reciprocal,
       r.slot AS their_slot, r.action AS their_action
FROM "Match" m
LEFT JOIN "Match" r
       ON r.user_id = m.candidate_id
      AND r.candidate_id = m.user_id
      AND r.week = m.week
WHERE m.week = 1
ORDER BY reciprocal DESC, m.user_id, m.slot;


-- ── 5. Where is a given pair up to? ───────────────────────────────────
-- Substitute the two ids from query 3 in all four places. Shows the
-- lock-in, the plan, both ceremony rows and the outcome one line each --
-- the fastest way to see which step of the walkthrough has happened.

SELECT 'lockin' AS thing, l.id, l.status AS state, l.created_at AS detail
FROM "LockIn" l
WHERE l.user_a IN ('u_0106','u_0143') OR l.user_b IN ('u_0106','u_0143')
UNION ALL
SELECT 'dateplan', p.id, p.status, p.datetime
FROM "DatePlan" p JOIN "LockIn" l ON l.id = p.lockin_id
WHERE l.user_a IN ('u_0106','u_0143') OR l.user_b IN ('u_0106','u_0143')
UNION ALL
SELECT 'ceremony', c.id, c.kind || ' / ' ||
       CASE WHEN c.completed_at IS NOT NULL THEN 'complete'
            WHEN c.face_verified = 1        THEN 'face done'
            WHEN c.signed_name IS NOT NULL  THEN 'signed'
            WHEN c.playbook_ack = 1         THEN 'playbook read'
            ELSE 'started' END,
       coalesce(c.signed_name, '-')
FROM "Ceremony" c WHERE c.user_id IN ('u_0106','u_0143')
UNION ALL
SELECT 'outcome', o.id,
       coalesce(o.a_decision,'-') || ' / ' || coalesce(o.b_decision,'-'),
       o.a_green_flags_json || ' ' || o.b_green_flags_json
FROM "DateOutcome" o
JOIN "DatePlan" p ON p.id = o.dateplan_id
JOIN "LockIn" l ON l.id = p.lockin_id
WHERE l.user_a IN ('u_0106','u_0143') OR l.user_b IN ('u_0106','u_0143');
