import sqlite3

db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
print("TABLES:", tables)

for t in tables:
    if 'extra' in t[0] or 'spool' in t[0] or 'field' in t[0]:
        print(f"\n--- {t[0]} ---")
        cur.execute(f"PRAGMA table_info({t[0]});")
        print(cur.fetchall())
        
conn.close()
