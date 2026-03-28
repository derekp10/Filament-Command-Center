import sqlite3
db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT used_weight, initial_weight FROM spool WHERE id = 142")
print('SPOOL 142 WEIGHT BEFORE:', cur.fetchone())
cur.execute("UPDATE spool SET used_weight = 100.0 WHERE id = 142")
conn.commit()
print("UPDATED.")
conn.close()
