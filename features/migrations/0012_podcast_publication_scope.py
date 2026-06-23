from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('features', '0011_socialfeedentry'),
    ]

    operations = [
        migrations.AddField(
            model_name='podcast',
            name='publication_scope',
            field=models.CharField(
                choices=[('draft', 'Draft'), ('website', 'Website'), ('internal', 'Internal Community')],
                default='draft',
                max_length=20,
            ),
        ),
    ]
