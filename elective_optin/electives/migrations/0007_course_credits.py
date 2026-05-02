from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('electives', '0006_redesign'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='credits',
            field=models.IntegerField(default=3),
        ),
    ]
