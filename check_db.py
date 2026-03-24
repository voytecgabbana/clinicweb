import sqlite3

conn = sqlite3.connect("medical.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tabele w bazie:", [t[0] for t in tables])
conn.close()
import sqlite3

conn = sqlite3.connect("medical.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(appointments);")
for row in cur.fetchall():
    print(row[1], row[2])

conn.close()