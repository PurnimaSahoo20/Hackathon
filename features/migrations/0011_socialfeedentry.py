from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('features', '0010_remove_teamevaluationassignment_expert_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocialFeedEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('platform', models.CharField(choices=[('instagram', 'Instagram'), ('facebook', 'Facebook'), ('youtube', 'YouTube'), ('twitter', 'Twitter / X'), ('linkedin', 'LinkedIn'), ('website', 'Website'), ('other', 'Other')], default='instagram', max_length=30)),
                ('published_date', models.DateField()),
                ('external_url', models.URLField()),
                ('is_published', models.BooleanField(default=True)),
                ('is_suspended', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('hackathon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_feeds', to='events.hackathon')),
            ],
            options={
                'db_table': 'features_socialfeedentry',
                'ordering': ['-published_date', '-created_at'],
            },
        ),
    ]
