from django.db import connection
cursor = connection.cursor()

def print_columns(table_name):
    cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}';")
    print(f"\n--- {table_name} ---")
    print([r[0] for r in cursor.fetchall()])

print_columns('accounts_problemstatement')
print_columns('accounts_creativematerial')
print_columns('accounts_team')
print_columns('accounts_venue')
print_columns('accounts_eventbudget')
