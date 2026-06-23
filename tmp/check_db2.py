from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'accounts_hackathon';")
columns = [r[0] for r in cursor.fetchall()]
print("\n--- DB COLUMNS START ---")
print(columns)
print("--- DB COLUMNS END ---\n")
