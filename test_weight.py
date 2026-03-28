import sqlite3
db_path = r'\\TRUENAS\App_Data\Spoolman\SPOOLMAN_DIR_DATA\spoolman.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute('SELECT used_weight, initial_weight FROM spool WHERE id = 1')
print('SPOOL 1:', cur.fetchone())
conn.close()
