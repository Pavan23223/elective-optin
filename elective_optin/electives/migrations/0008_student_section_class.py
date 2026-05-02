from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('electives', '0007_course_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='section',
            field=models.CharField(blank=True, default='A', max_length=5),
        ),
        migrations.AddField(
            model_name='student',
            name='class_name',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
