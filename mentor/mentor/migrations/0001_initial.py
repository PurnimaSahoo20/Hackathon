from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0018_auditlog'),
        ('events', '0003_hackathon_created_by_round_activation'),
        ('features', '0005_add_venue_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='MentorInvitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mentor_name', models.CharField(max_length=255)),
                ('mentor_email', models.EmailField()),
                ('token', models.CharField(max_length=64, unique=True)),
                ('status', models.CharField(choices=[
                    ('invited', 'Invited'), ('accepted', 'Accepted by Mentor'),
                    ('spoc_pending', 'Pending SPOC Verification'), ('spoc_approved', 'SPOC Approved'),
                    ('spoc_rejected', 'SPOC Rejected'), ('admin_approved', 'Admin Approved'),
                    ('admin_rejected', 'Admin Rejected'), ('active', 'Active'),
                ], default='invited', max_length=30)),
                ('mentor_designation', models.CharField(blank=True, max_length=255)),
                ('mentor_institution', models.CharField(blank=True, max_length=255)),
                ('mentor_phone', models.CharField(blank=True, max_length=20)),
                ('mentor_expertise', models.CharField(blank=True, max_length=255)),
                ('id_proof', models.FileField(blank=True, null=True, upload_to='mentor_id_proofs/')),
                ('invited_at', models.DateTimeField(auto_now_add=True)),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('spoc_decided_at', models.DateTimeField(blank=True, null=True)),
                ('admin_decided_at', models.DateTimeField(blank=True, null=True)),
                ('spoc_note', models.TextField(blank=True)),
                ('admin_note', models.TextField(blank=True)),
                ('team_leader', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentor_invitations_sent', to='accounts.user')),
                ('registration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mentor_invitations', to='features.teamregistration')),
                ('hackathon', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='events.hackathon')),
                ('created_user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='from_mentor_invitation', to='accounts.user')),
            ],
            options={'ordering': ['-invited_at']},
        ),
        migrations.CreateModel(
            name='MentorNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[
                    ('invite', 'Invitation Received'), ('spoc_update', 'SPOC Update'),
                    ('admin_update', 'Admin Update'), ('team_msg', 'Team Message'), ('system', 'System'),
                ], default='system', max_length=30)),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField(blank=True)),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('mentor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentor_notifications', to='accounts.mentorprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='MentorMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentor_sent', to='accounts.user')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentor_received', to='accounts.user')),
            ],
            options={'ordering': ['sent_at']},
        ),
    ]
