from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_alter_spocinvitation_hackathon_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='spocinvitation',
            name='status',
            field=models.CharField(
                choices=[
                    ('invited', 'Invited'),
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('suspended', 'Suspended'),
                ],
                default='invited',
                max_length=20,
            ),
        ),
    ]
