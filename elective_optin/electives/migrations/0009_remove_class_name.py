from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('electives', '0008_student_section_class'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='student',
            name='class_name',
        ),
    ]
