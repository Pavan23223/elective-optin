from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('electives', '0005_preference_rank'),
    ]

    operations = [
        # Add salient_features to Course
        migrations.AddField(
            model_name='course',
            name='salient_features',
            field=models.TextField(blank=True, default=''),
        ),
        # Add is_published to Course
        migrations.AddField(
            model_name='course',
            name='is_published',
            field=models.BooleanField(default=False),
        ),
        # Add current_semester to Student
        migrations.AddField(
            model_name='student',
            name='current_semester',
            field=models.IntegerField(default=1),
        ),
        # Remove class_name from StudentSemester (cleanup)
        migrations.RemoveField(
            model_name='studentsemester',
            name='class_name',
        ),
        # Remove ChangeRequest model
        migrations.DeleteModel(
            name='ChangeRequest',
        ),
        # Fix unique_together on Preference to also include (student, course)
        migrations.AlterUniqueTogether(
            name='preference',
            unique_together={('student', 'rank'), ('student', 'course')},
        ),
    ]
