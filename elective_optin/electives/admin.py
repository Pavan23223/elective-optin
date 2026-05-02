from django.contrib import admin
from .models import Department, Student, StudentSemester, StudentCourseHistory, Course, Preference

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'category', 'semester', 'seats', 'available_seats', 'is_published']
    list_filter = ['department', 'category', 'semester', 'is_published']
    list_editable = ['is_published']
    search_fields = ['name']
    actions = ['publish_courses', 'unpublish_courses']

    def publish_courses(self, request, queryset):
        queryset.update(is_published=True)
        self.message_user(request, f"{queryset.count()} course(s) published.")
    publish_courses.short_description = "Publish selected courses"

    def unpublish_courses(self, request, queryset):
        queryset.update(is_published=False)
        self.message_user(request, f"{queryset.count()} course(s) unpublished.")
    unpublish_courses.short_description = "Unpublish selected courses"


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['usn', 'name', 'department', 'current_semester']
    list_filter = ['department']
    search_fields = ['usn', 'name']


@admin.register(Preference)
class PreferenceAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'rank', 'status', 'timestamp']
    list_filter = ['status', 'course__department']


admin.site.register(Department)
admin.site.register(StudentSemester)
admin.site.register(StudentCourseHistory)
