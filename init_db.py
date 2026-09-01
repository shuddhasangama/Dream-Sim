import sqlite3
import os

os.makedirs("data", exist_ok=True)

with open("schema.sql", "r") as f:
    schema = f.read()

conn = sqlite3.connect("data/dream.db")
conn.executescript(schema)
conn.commit()
conn.close()

print("Database created at data/dream.db")