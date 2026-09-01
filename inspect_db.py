import sqlite3

conn = sqlite3.connect("data/dream.db")
cur = conn.cursor()

# list every table
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]

print(f"\n{len(tables)} TABLES FOUND\n" + "="*50)
for t in tables:
    print(f"\n{t}")
    cur.execute(f"PRAGMA table_info({t})")
    for col in cur.fetchall():
        # col = (id, name, type, notnull, default, pk)
        pk = " [PK]" if col[5] else ""
        print(f"    {col[1]:<28} {col[2]}{pk}")

# guardrail check
banned = ["skin", "tone", "complexion", "appearance", "colour", "color", "fairness"]
conn = sqlite3.connect("data/dream.db")
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table'")
schema_text = " ".join(r[0].lower() for r in cur.fetchall() if r[0])
hits = [w for w in banned if w in schema_text]
print("\n" + "="*50)
print("GUARDRAIL:", "FAIL — found " + ", ".join(hits) if hits else "PASS — no appearance fields")

conn.close()