-- ═══════════════════════════════════════════════════════════════════════
--  find-test-pair.sql — who can actually be matched, on the live database
--
--  HOW TO RUN THIS. Railway's Console tab on a Postgres service is a
--  SHELL, not a query editor: pasting SQL there hands it to bash, which
--  answers "syntax error near unexpected token `('". Two ways that work:
--
--    From your machine (easiest):
--        set DB_URL=<DATABASE_PUBLIC_URL from the Variables tab>
--        run-sql.cmd find-test-pair.sql
--
--    In the Railway Console, start a client first:
--        psql -U postgres -d railway
--    then paste one query at a time. \q to exit.
--
--  Read-only.
--
--  WHY THIS EXISTS
--  The population in Railway was seeded by an OLDER generate_users.py.
--  Stats fields added since (budget, ethnicity, cuisine, smoking,
--  drinking, fitness_routine) each consume RNG draws, which shifts the
--  whole stream — so regenerating locally with the same seed now produces
--  a DIFFERENT population. The deployed database is the only source of
--  truth for who is in it. Hence: query it, do not recompute it.
-- ═══════════════════════════════════════════════════════════════════════


-- ── 1. WHAT IS ACTUALLY IN THERE ───────────────────────────────────────
-- Sanity check before anything else. The last column counts users whose
-- distance filter has a MINIMUM above zero — every inter-city gap in
-- matching._CITY_DISTANCES_KM is >= 120 km and no generated distance_max
-- reaches that, so those users can never match anyone, in any week.

SELECT journey_state, bgv_status, count(*),
       count(*) FILTER (WHERE (preferences_json::jsonb->'adjustable'->'distance_km'->>0)::numeric > 0)
         AS unmatchable_distance_min
FROM "User" GROUP BY 1,2 ORDER BY 1,2;


-- ── 2. THE PAIRS — run this one ────────────────────────────────────────
-- Every mutually-open verified pair. This is matching.mutual_open()
-- rewritten in SQL: gender, distance, the four range levers both ways,
-- nationality, religion tiers, and the three enforced dealbreakers.
-- Validated against the Python original over four populations of 300
-- users (27 pairs, zero disagreements).
WITH u AS (
  SELECT
    id,
    stats_json::jsonb        AS s,
    preferences_json::jsonb  AS p,
    vision_json::jsonb       AS v,
    stats_json::jsonb ->> 'city'        AS city,
    stats_json::jsonb ->> 'gender'      AS gender,
    stats_json::jsonb ->> 'religion'    AS religion,
    stats_json::jsonb ->> 'nationality' AS nationality,
    stats_json::jsonb ->> 'diet'        AS diet,
    (stats_json::jsonb ->> 'age')::numeric       AS age,
    (stats_json::jsonb ->> 'height_cm')::numeric AS height_cm,
    (stats_json::jsonb ->> 'weight_kg')::numeric AS weight_kg,
    (stats_json::jsonb ->> 'waist_in')::numeric  AS waist_in,
    EXISTS (SELECT 1 FROM jsonb_array_elements(vision_json::jsonb) e
            WHERE e ->> 'key' = 'Kids')          AS wants_kids
  FROM "User"
  WHERE bgv_status = 'verified' AND journey_state = 'dating'
),
fam AS (SELECT * FROM (VALUES
  ('Hindu','dharmic'),('Sikh','dharmic'),('Spiritual','dharmic'),
  ('Muslim','abrahamic'),('Christian','abrahamic'),('None','unaffiliated')
) AS t(religion, family))
SELECT a.id AS user_a, b.id AS user_b, a.city,
       a.gender AS a_gender, a.age AS a_age, a.diet AS a_diet,
       b.gender AS b_gender, b.age AS b_age, b.diet AS b_diet
FROM u a
JOIN u b ON b.id > a.id
LEFT JOIN fam fa ON fa.religion = a.religion
LEFT JOIN fam fb ON fb.religion = b.religion
WHERE a.gender <> b.gender
  -- Distance. Every inter-city gap in matching._CITY_DISTANCES_KM is
  -- >= 120 km and no generated distance_max reaches that, so a match is
  -- always same-city (distance 0) — which also needs distance_min = 0.
  AND a.city = b.city
  AND (a.p -> 'adjustable' -> 'distance_km' ->> 0)::numeric = 0
  AND (b.p -> 'adjustable' -> 'distance_km' ->> 0)::numeric = 0
  -- The four range levers, checked in BOTH directions.
  AND b.age       BETWEEN (a.p->'adjustable'->'age'->>0)::numeric       AND (a.p->'adjustable'->'age'->>1)::numeric
  AND b.height_cm BETWEEN (a.p->'adjustable'->'height_cm'->>0)::numeric AND (a.p->'adjustable'->'height_cm'->>1)::numeric
  AND b.weight_kg BETWEEN (a.p->'adjustable'->'weight_kg'->>0)::numeric AND (a.p->'adjustable'->'weight_kg'->>1)::numeric
  AND b.waist_in  BETWEEN (a.p->'adjustable'->'waist_in'->>0)::numeric  AND (a.p->'adjustable'->'waist_in'->>1)::numeric
  AND a.age       BETWEEN (b.p->'adjustable'->'age'->>0)::numeric       AND (b.p->'adjustable'->'age'->>1)::numeric
  AND a.height_cm BETWEEN (b.p->'adjustable'->'height_cm'->>0)::numeric AND (b.p->'adjustable'->'height_cm'->>1)::numeric
  AND a.weight_kg BETWEEN (b.p->'adjustable'->'weight_kg'->>0)::numeric AND (b.p->'adjustable'->'weight_kg'->>1)::numeric
  AND a.waist_in  BETWEEN (b.p->'adjustable'->'waist_in'->>0)::numeric  AND (b.p->'adjustable'->'waist_in'->>1)::numeric
  -- Nationality: "Any" in the accepted list, or an exact match.
  AND (a.p->'adjustable'->'nationality' @> '["Any"]'::jsonb OR a.p->'adjustable'->'nationality' @> to_jsonb(b.nationality))
  AND (b.p->'adjustable'->'nationality' @> '["Any"]'::jsonb OR b.p->'adjustable'->'nationality' @> to_jsonb(a.nationality))
  -- Religion tiers: any / same / related (same family).
  AND (a.p->'adjustable'->'religion' @> '["any"]'::jsonb
       OR (a.p->'adjustable'->'religion' @> '["same"]'::jsonb AND b.religion = a.religion)
       OR (a.p->'adjustable'->'religion' @> '["related"]'::jsonb AND fb.family = fa.family))
  AND (b.p->'adjustable'->'religion' @> '["any"]'::jsonb
       OR (b.p->'adjustable'->'religion' @> '["same"]'::jsonb AND a.religion = b.religion)
       OR (b.p->'adjustable'->'religion' @> '["related"]'::jsonb AND fa.family = fb.family))
  -- Dealbreakers. non_smoker / non_drinker are vacuously satisfied in
  -- matching.py, so they are deliberately not checked here either.
  AND (NOT a.p->'fixed'->'dealbreakers' @> '["veg_only"]'::jsonb       OR b.diet IN ('Vegetarian','Vegan','Jain'))
  AND (NOT b.p->'fixed'->'dealbreakers' @> '["veg_only"]'::jsonb       OR a.diet IN ('Vegetarian','Vegan','Jain'))
  AND (NOT a.p->'fixed'->'dealbreakers' @> '["wants_kids"]'::jsonb     OR b.wants_kids)
  AND (NOT b.p->'fixed'->'dealbreakers' @> '["wants_kids"]'::jsonb     OR a.wants_kids)
  AND (NOT a.p->'fixed'->'dealbreakers' @> '["no_kids_wanted"]'::jsonb OR NOT b.wants_kids)
  AND (NOT b.p->'fixed'->'dealbreakers' @> '["no_kids_wanted"]'::jsonb OR NOT a.wants_kids)
ORDER BY a.city, a.id;


-- ── 3. THE MATCH TABLE, WEEK 1 ─────────────────────────────────────────
-- Yes — "Match" is the table. One row per (user, week, slot), written
-- LAZILY: a user's rows do not exist until they open /week for that week.
-- So an empty result here means nobody has looked yet, not that nobody
-- can match.
--
-- Everything one user was shown in week 1:

SELECT m.user_id, m.slot, m.candidate_id, m.action, m.revealed_at, m.window_closes_at
FROM "Match" m
WHERE m.week = 1 AND m.user_id = 'u_0106'   -- <— put a real id here
ORDER BY m.slot;


-- Reciprocal pairs — each has the other in their own list, which is what
-- a lock-in needs. Exact, because a Match row only exists if
-- mutual_open() already passed.

SELECT a.user_id AS user_a, a.slot AS a_sees_them_in_slot,
       b.user_id AS user_b, b.slot AS b_sees_them_in_slot,
       a.action AS a_action, b.action AS b_action
FROM "Match" a
JOIN "Match" b
  ON b.user_id = a.candidate_id
 AND b.candidate_id = a.user_id
 AND b.week = a.week
WHERE a.week = 1 AND a.user_id < b.user_id
ORDER BY a.slot, b.slot, a.user_id;


-- ── 4. NAMES ───────────────────────────────────────────────────────────
-- The picker's names are NOT stored — app.display_name() derives them
-- from (user_id, gender) at render time, so there is no name column to
-- query. Take the ids from query 2 and find them with:
--
--   python -c "import random;
--   F={'female':['Priya','Ananya','Meera','Kavya','Isha','Riya','Sneha','Tara','Divya','Neha','Pooja','Simran'],
--      'male':['Arjun','Rohan','Vikram','Aditya','Karan','Rahul','Aryan','Dev','Nikhil','Siddharth','Varun','Ishaan']};
--   L=['Sharma','Mehta','Iyer','Rao','Kapoor','Nair','Reddy','Bhatt','Chopra','Menon','Gupta','Desai'];
--   r=random.Random('u_0106'); print(r.choice(F['female']), r.choice(L))"
--
-- Or skip the picker entirely — POST to /login/<id> from the browser
-- console on the deployed site:
--
--   fetch('/login/u_0106', {method:'POST'}).then(() => location = '/guru')
