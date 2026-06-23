import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_spocinvitation_suspended_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actor_username', models.CharField(blank=True, max_length=150)),
                ('actor_email', models.EmailField(blank=True, max_length=254)),
                ('action', models.CharField(choices=[('create', 'Create'), ('update', 'Update'), ('delete', 'Delete')], db_index=True, max_length=20)),
                ('app_label', models.CharField(db_index=True, max_length=100)),
                ('model_name', models.CharField(db_index=True, max_length=100)),
                ('object_pk', models.CharField(db_index=True, max_length=255)),
                ('object_repr', models.TextField(blank=True)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('snapshot', models.JSONField(blank=True, default=dict)),
                ('request_method', models.CharField(blank=True, max_length=10)),
                ('request_path', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='accounts.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['app_label', 'model_name', 'object_pk'], name='accounts_au_app_lab_305a72_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['actor', 'created_at'], name='accounts_au_actor_i_670b11_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['action', 'created_at'], name='accounts_au_action_c683b9_idx'),
        ),
    ]
