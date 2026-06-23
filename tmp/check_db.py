import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hackathon.settings")
django.setup()

from django.db import connection

cursor = connection.cursor()
cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'accounts_hackathon';")
print([r[0] for r in cursor.fetchall()])
