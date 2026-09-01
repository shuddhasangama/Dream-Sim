import sqlite3

conn = sqlite3.connect("data/dream.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM User LIMIT 50")
rows = cur.fetchall()

print(f"\n{len(rows)} USERS\n" + "="*70)
for r in rows:
    d = dict(r)
    print(f"{d.get('id','?'):<6} {d.get('name','?'):<18} "
          f"{d.get('gender','?'):<8} {d.get('age','?'):<4} {d.get('city','?')}")

# quick distribution check
print("\n" + "="*70)
for field in ("gender", "city"):
    cur.execute("SELECT {field}, COUNT(*) FROM User GROUP BY {field}")
    print(f"\n{field.upper()}:")
    for val, count in cur.fetchall():
        print(f"   {val:<20} {count}")
conn.close()