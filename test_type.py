import sqlite3
import json
db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT filament_id, key, value FROM filament_field WHERE key = 'filament_attributes' LIMIT 10")
for r in cur.fetchall():
    print(r[0], repr(r[1]), repr(r[2]))
conn.close()
