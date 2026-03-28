import sqlite3
import json
db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT key, value FROM spool_field WHERE spool_id = 142')
print("SPOOL 142:")
for r in cur.fetchall():
    print(r[0], repr(r[1]))
    try:
        print('    JSON:', repr(json.loads(r[1])))
    except Exception as e:
        print('    JSON ERROR:', e)
conn.close()
