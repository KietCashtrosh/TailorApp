import sqlite3
conn = sqlite3.connect('tailor_app.db')
rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables in tailor_app.db:", rows)
conn.close()
