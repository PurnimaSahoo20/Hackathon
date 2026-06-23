from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0018_auditlog'),
        ('features', '0005_add_venue_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpocDashboardActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('icon', models.CharField(default='📋', max_length=10)),
                ('color', models.CharField(default='#2563eb', max_length=30)),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('spoc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dashboard_activities', to='accounts.spocprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='SpocTeamApproval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('auth_letter', models.FileField(blank=True, null=True, upload_to='spoc/auth_letters/')),
                ('rejection_reason', models.TextField(blank=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spoc_approvals', to='features.teamregistration')),
                ('spoc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_approvals', to='accounts.spocprofile')),
            ],
            options={'ordering': ['-created_at'], 'unique_together': {('spoc', 'registration')}},
        ),
        migrations.CreateModel(
            name='SpocModificationDecision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_name', models.CharField(max_length=255)),
                ('requested_change', models.CharField(max_length=500)),
                ('reason', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('auth_letter', models.FileField(blank=True, null=True, upload_to='spoc/mod_letters/')),
                ('rejection_reason', models.TextField(blank=True)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('spoc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mod_decisions', to='accounts.spocprofile')),
            ],
            options={'ordering': ['-requested_at']},
        ),
        migrations.CreateModel(
            name='SpocMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spoc_sent_messages', to='accounts.user')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='spoc_received_messages', to='accounts.user')),
            ],
            options={'ordering': ['sent_at']},
        ),
        migrations.CreateModel(
            name='SpocNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[('team_reg', 'New Team Registration'), ('mod_req', 'Modification Request'), ('admin_msg', 'Admin Message'), ('system', 'System')], default='system', max_length=30)),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField(blank=True)),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('spoc', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.spocprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
