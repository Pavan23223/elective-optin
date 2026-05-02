from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('catalog/', views.catalog, name='catalog'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('student-login/', views.student_login, name='student_login'),
    path('change-password/', views.change_password, name='change_password'),

    # Department
    path('dashboard/', views.department_dashboard, name='dashboard'),
    path('dept-upload-students/', views.dept_upload_students, name='dept_upload_students'),
    path('dept-delete-student/<int:student_id>/', views.dept_delete_student, name='dept_delete_student'),
    path('dept-delete-course/<int:course_id>/', views.dept_delete_course, name='dept_delete_course'),
    path('dept-edit-course/<int:course_id>/', views.dept_edit_course, name='dept_edit_course'),
    path('dept-bulk-delete-students/', views.dept_bulk_delete_students, name='dept_bulk_delete_students'),

    # Main Admin — Override
    path('admin-panel/', views.main_admin_dashboard, name='main_admin'),
    path('override/', views.override_panel, name='override_panel'),
    path('override/cancel/<int:pref_id>/', views.override_cancel, name='override_cancel'),
    path('override/force-allocate/', views.override_force_allocate, name='override_force_allocate'),
    path('publish/<int:course_id>/', views.publish_course, name='publish_course'),
    path('unpublish/<int:course_id>/', views.unpublish_course, name='unpublish_course'),
    path('delete-course/<int:course_id>/', views.delete_course, name='delete_course'),
    path('edit-course/<int:course_id>/', views.edit_course, name='edit_course'),
    path('bulk-publish/', views.bulk_publish, name='bulk_publish'),
    path('allocate/', views.run_allocation, name='run_allocation'),
    path('export/', views.export_csv, name='export'),
    path('upload-students/', views.upload_students, name='upload_students'),
    path('delete-student/<int:student_id>/', views.delete_student, name='delete_student'),
    path('download-student-template/', views.download_student_template, name='download_student_template'),
    path('export-students/', views.export_students, name='export_students'),
    path('download-courses-groupwise/', views.download_courses_groupwise, name='download_courses_groupwise'),
    path('download-allocation-details/', views.download_allocation_details, name='download_allocation_details'),
    path('download-course-students/<int:course_id>/', views.download_course_students, name='download_course_students'),

    # Student
    path('student-dashboard/', views.student_dashboard, name='student_dashboard'),
    path('select/<int:course_id>/', views.submit_preference, name='select'),
    path('results/', views.results, name='results'),
    path('edit-student-profile/', views.edit_student_profile, name='edit_student_profile'),

    # Admin/Department Profile
    path('edit-admin-profile/', views.edit_admin_profile, name='edit_admin_profile'),
    path('admin-edit-profile/', views.admin_edit_profile, name='admin_edit_profile'),

    # AJAX
    path('get-seats/', views.get_seats, name='get_seats'),
]
