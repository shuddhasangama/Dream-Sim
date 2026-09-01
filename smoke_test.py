from generate_users import load_users        # adjust import names to match yours
from matching import reciprocity_counts, whatif_deltas
from cadence import run_week

pool = load_users()                          # your 50 users
u = pool[0]

print(f"USER: {u['name']}, {u['age']}, {u['city']}")
rc = reciprocity_counts(u, pool)
print(f"  fits their filters : {rc['fits_user_filters']}")
print(f"  mutually open      : {rc['mutual_open']}")

print("\nWHAT-IF:")
for d in whatif_deltas(u, pool):
    print(f"  {d['lever']:<16} +{d['delta_mutual_open']}")

print("\nWEEK 1:")
result = run_week(pool, 1)
print(f"  lock-ins: {len(result.get('lock_ins', []))}")
print(f"  users with zero matches: {result.get('zero_match_users', '?')}")