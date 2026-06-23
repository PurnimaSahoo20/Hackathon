from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_auditlog'),
        ('events', '0002_remove_hackathon_created_by'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS created_by_id bigint NULL;"),
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS round_1_is_enabled boolean NOT NULL DEFAULT true;"),
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS round_2_is_enabled boolean NOT NULL DEFAULT true;"),
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS round_3_is_enabled boolean NOT NULL DEFAULT true;"),
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS round_4_is_enabled boolean NOT NULL DEFAULT true;"),
                migrations.RunSQL("ALTER TABLE accounts_hackathon ADD COLUMN IF NOT EXISTS round_5_is_enabled boolean NOT NULL DEFAULT true;"),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='hackathon',
                    name='created_by',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='accounts.superadminprofile'),
                ),
                migrations.AddField(
                    model_name='hackathon',
                    name='round_1_is_enabled',
                    field=models.BooleanField(default=True),
                ),
                migrations.AddField(
                    model_name='hackathon',
                    name='round_2_is_enabled',
                    field=models.BooleanField(default=True),
                ),
                migrations.AddField(
                    model_name='hackathon',
                    name='round_3_is_enabled',
                    field=models.BooleanField(default=True),
                ),
                migrations.AddField(
                    model_name='hackathon',
                    name='round_4_is_enabled',
                    field=models.BooleanField(default=True),
                ),
                migrations.AddField(
                    model_name='hackathon',
                    name='round_5_is_enabled',
                    field=models.BooleanField(default=True),
                ),
            ],
        ),
    ]
