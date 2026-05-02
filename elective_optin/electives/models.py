from django.db import models
from django.contrib.auth.models import User

# Department Groups - students cannot take courses from their own group
IT_DEPARTMENTS = ['CSE', 'ISE', 'AIML', 'CSDS']
MECHANICAL_DEPARTMENTS = ['ME', 'MECHANICAL', 'MECH']
CIVIL_DEPARTMENTS = ['CE', 'CIVIL']
EC_EEE_DEPARTMENTS = ['EC', 'EEE', 'ECE', 'EE', 'ELECTRONICS', 'ELECTRICAL']

# All department groups
DEPARTMENT_GROUPS = [
    IT_DEPARTMENTS,
    MECHANICAL_DEPARTMENTS, 
    CIVIL_DEPARTMENTS,
    EC_EEE_DEPARTMENTS
]

# -----------------------------
# Department
# -----------------------------
class Department(models.Model):
    name = models.CharField(max_length=100)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

    def is_it_dept(self):
        return self.name.upper() in IT_DEPARTMENTS
    
    def get_department_group(self):
        """Get the department group this department belongs to"""
        dept_name_upper = self.name.upper()
        for group in DEPARTMENT_GROUPS:
            if dept_name_upper in group:
                return group
        return None
    
    def is_same_group(self, other_department):
        """Check if this department is in the same group as another department"""
        if not other_department:
            return False
        
        my_group = self.get_department_group()
        other_group = other_department.get_department_group()
        
        if my_group and other_group:
            return my_group == other_group
        return False


# -----------------------------
# Student
# -----------------------------
class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    usn = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    current_semester = models.IntegerField(default=1)
    section = models.CharField(max_length=5, blank=True, default='A')
    must_change_password = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.usn} - {self.name}"

    def cgpa(self):
        latest = self.studentsemester_set.order_by('-semester').first()
        return latest.cgpa if latest else 0.0


# -----------------------------
# Student Semester (CGPA per sem)
# -----------------------------
class StudentSemester(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    semester = models.IntegerField()
    cgpa = models.FloatField()

    def __str__(self):
        return f"{self.student.usn} - Sem {self.semester}"


# -----------------------------
# Student Course History
# -----------------------------
class StudentCourseHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course_name = models.CharField(max_length=200)
    semester = models.IntegerField()

    def __str__(self):
        return f"{self.student.usn} - {self.course_name}"


# -----------------------------
# Course
# -----------------------------
CATEGORY_CHOICES = [
    ('professional', 'Professional Elective'),
    ('open', 'Open Elective'),
    ('ability', 'Ability Enhancement'),
]

class Course(models.Model):
    name = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='open')
    salient_features = models.TextField(blank=True, default='')
    job_perspective = models.TextField(blank=True, default='')
    prerequisites = models.TextField(blank=True, default='None')
    credits = models.IntegerField(default=3, help_text="Number of credits for this course")
    seats = models.IntegerField(default=30)
    available_seats = models.IntegerField(default=30)
    semester = models.IntegerField(default=1, help_text="Semester this course is offered for")
    is_published = models.BooleanField(default=False, help_text="Admin publishes to make visible to students")

    def __str__(self):
        return f"{self.name} ({self.department.name} - Sem {self.semester})"

# Preference (Student choice)
class Preference(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    rank = models.IntegerField(default=1)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='pending')

    class Meta:
        unique_together = [('student', 'rank'), ('student', 'course')]
        ordering = ['rank']

    def __str__(self):
        return f"{self.student.usn} -> {self.course.name} (Rank {self.rank})"
