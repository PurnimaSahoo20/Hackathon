from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'accounts_podcast';")
print("Podcast:", [r[0] for r in cursor.fetchall()])
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'accounts_documentation';")
print("Documentation:", [r[0] for r in cursor.fetchall()])
