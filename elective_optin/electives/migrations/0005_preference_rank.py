from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('electives', '0004_student_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='preference',
            name='rank',
            field=models.IntegerField(default=1),
        ),
        migrations.AlterUniqueTogether(
            name='preference',
            unique_together={('student', 'rank')},
        ),
        migrations.AlterModelOptions(
            name='preference',
            options={'ordering': ['rank']},
        ),
    ]
