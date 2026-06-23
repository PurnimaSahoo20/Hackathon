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
            name='TeamMemberInvite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField()),
                ('name', models.CharField(blank=True, max_length=255)),
                ('role', models.CharField(default='Member', max_length=100)),
                ('token', models.CharField(max_length=64, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')], default='pending', max_length=20)),
                ('invited_at', models.DateTimeField(auto_now_add=True)),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='member_invites', to='features.teamregistration')),
                ('inviter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_member_invites', to='accounts.user')),
            ],
            options={'ordering': ['-invited_at']},
        ),
        migrations.CreateModel(
            name='TeamNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[
                    ('mentor_accepted', 'Mentor Accepted'), ('mentor_rejected', 'Mentor Rejected'),
                    ('spoc_approved', 'SPOC Approved'), ('spoc_rejected', 'SPOC Rejected'),
                    ('admin_approved', 'Admin Approved'), ('member_joined', 'Member Joined'),
                    ('system', 'System'),
                ], default='system', max_length=30)),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField(blank=True)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('team_leader', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_notifications', to='accounts.user')),
                ('registration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='features.teamregistration')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='TeamSolution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('doc_type', models.CharField(choices=[
                    ('ppt', 'Presentation'), ('report', 'Report / Document'),
                    ('code', 'Code / Zip'), ('video', 'Demo Video URL'), ('other', 'Other'),
                ], default='other', max_length=20)),
                ('file', models.FileField(blank=True, null=True, upload_to='team_solutions/')),
                ('video_url', models.URLField(blank=True)),
                ('description', models.TextField(blank=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('registration', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='solutions', to='features.teamregistration')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.user')),
            ],
            options={'ordering': ['-uploaded_at']},
        ),
    ]
