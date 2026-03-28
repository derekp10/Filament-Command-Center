import sqlite3
db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE name='spool'")
print(cur.fetchone()[0])
conn.close()
