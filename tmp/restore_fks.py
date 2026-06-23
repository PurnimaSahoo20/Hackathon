from django.db import connection

queries = [
    "ALTER TABLE accounts_creativematerial ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_documentation ADD COLUMN IF NOT EXISTS created_by_id bigint NULL;",
    "ALTER TABLE accounts_documentation ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_documentation ADD COLUMN IF NOT EXISTS problem_statement_id bigint NULL;",
    "ALTER TABLE accounts_eventbudget ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_financialtransaction ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_financialtransaction ADD COLUMN IF NOT EXISTS processed_by_id bigint NULL;",
    "ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS created_by_id bigint NULL;",
    "ALTER TABLE accounts_team ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_problemstatement ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_venue ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;",
    "ALTER TABLE accounts_teamregistration ADD COLUMN IF NOT EXISTS hackathon_id bigint NULL;"
]

with connection.cursor() as cursor:
    for q in queries:
        try:
            cursor.execute(q)
            print("Executed:", q)
        except Exception as e:
            print("Failed:", q, e)

print("Foreign Key Columns Restored.")
