from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('features', '0003_team_created_at_team_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='declared_member_count',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='team',
            name='leader_aadhaar_proof',
            field=models.FileField(blank=True, null=True, upload_to='team_documents/aadhaar/'),
        ),
        migrations.AddField(
            model_name='team',
            name='leader_college_id_proof',
            field=models.FileField(blank=True, null=True, upload_to='team_documents/college_ids/'),
        ),
        migrations.AddField(
            model_name='team',
            name='leader_role_in_team',
            field=models.CharField(default='Leader', max_length=100),
        ),
        migrations.AddField(
            model_name='teammember',
            name='aadhaar_proof',
            field=models.FileField(blank=True, null=True, upload_to='team_documents/aadhaar/'),
        ),
        migrations.AddField(
            model_name='teammember',
            name='college_id_proof',
            field=models.FileField(blank=True, null=True, upload_to='team_documents/college_ids/'),
        ),
    ]
