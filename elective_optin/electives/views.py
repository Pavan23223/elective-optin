from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import csv
import io

from .models import Student, Course, Department, Preference, StudentSemester, CATEGORY_CHOICES
from .utils import check_eligibility, allocate_electives, get_latest_cgpa, promote_waitlist, auto_allocate_pending
from .forms import CourseForm, ExportFilterForm


# ── Home ──────────────────────────────────────────────────────────────────────
def home(request):
    return render(request, 'electives/home.html')


# ── Auth ──────────────────────────────────────────────────────────────────────
def login_view(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get('username'),
                            password=request.POST.get('password'))
        if user:
            # Reject if this is a student account (has Student record, no Department)
            is_dept = Department.objects.filter(user=user).exists()
            if not user.is_superuser and not is_dept:
                messages.error(request, "Use the Student Login page instead.")
                return render(request, 'electives/login.html')
            login(request, user)
            if user.is_superuser:
                return redirect('main_admin')
            return redirect('dashboard')
        messages.error(request, "Invalid credentials. Please try again.")
    
    # Get all admin and department users for dropdown
    admin_users = []
    
    # Add super admin
    super_admins = User.objects.filter(is_superuser=True)
    for admin in super_admins:
        admin_users.append({
            'username': admin.username,
            'display_name': f'Super Admin ({admin.username})',
            'type': 'admin'
        })
    
    # Add department admins
    departments = Department.objects.filter(user__isnull=False).select_related('user')
    for dept in departments:
        admin_users.append({
            'username': dept.user.username,
            'display_name': f'{dept.name} Department',
            'type': 'department'
        })
    
    return render(request, 'electives/login.html', {'admin_users': admin_users})


def student_login(request):
    if request.method == "POST":
        user = authenticate(request, username=request.POST.get('usn'),
                            password=request.POST.get('password'))
        if user:
            # Reject dept/admin accounts on student login
            is_dept_or_admin = user.is_superuser or Department.objects.filter(user=user).exists()
            if is_dept_or_admin:
                messages.error(request, "This account is not a student account.")
                return render(request, 'electives/student_login.html')
            # Check student record exists
            if not Student.objects.filter(user=user).exists():
                messages.error(request, "No student profile found for this account.")
                return render(request, 'electives/student_login.html')
            login(request, user)
            return redirect('student_dashboard')
        messages.error(request, "Invalid USN or password.")
    return render(request, 'electives/student_login.html')


def logout_view(request):
    logout(request)
    return redirect('home')


def change_password(request):
    if not request.user.is_authenticated:
        return redirect('student_login')
    if request.method == "POST":
        new_pw = request.POST.get('new_password', '').strip()
        if len(new_pw) < 4:
            messages.error(request, "Password must be at least 4 characters.")
            return render(request, 'electives/change_password.html')
        request.user.set_password(new_pw)
        request.user.save()
        student = get_object_or_404(Student, user=request.user)
        student.must_change_password = False
        student.save()
        messages.success(request, "Password updated. Please log in again.")
        return redirect('student_login')
    return render(request, 'electives/change_password.html')


# ── Department Dashboard ───────────────────────────────────────────────────────
def department_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    department = get_object_or_404(Department, user=request.user)
    courses = Course.objects.filter(department=department).order_by('semester', 'name')

    total_seats = sum(c.seats for c in courses)
    filled_seats = sum(c.seats - c.available_seats for c in courses)

    tab = request.GET.get('tab', 'courses')

    # Student filters
    sem_filter     = request.GET.get('sem', '')
    section_filter = request.GET.get('section', '')

    students_qs = Student.objects.filter(department=department).order_by('current_semester', 'section', 'usn')
    if sem_filter:
        students_qs = students_qs.filter(current_semester=sem_filter)
    if section_filter:
        students_qs = students_qs.filter(section=section_filter)

    # All students for filter dropdowns
    all_students = Student.objects.filter(department=department)
    sem_choices     = sorted(set(all_students.values_list('current_semester', flat=True)))
    section_choices = sorted(set(all_students.values_list('section', flat=True)))

    # Add course POST
    if request.method == "POST" and 'add_course' in request.POST:
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.department = department
            course.available_seats = course.seats
            course.is_published = False
            course.save()
            messages.success(request, f"'{course.name}' added. Waiting for admin to publish.")
            return redirect('/dashboard/?tab=courses')
    else:
        form = CourseForm()

    preferences = Preference.objects.filter(
        course__department=department
    ).select_related('student', 'course').order_by('timestamp')

    # Filter preferences by course if specified
    course_filter = request.GET.get('course_filter')
    if course_filter:
        preferences = preferences.filter(course_id=course_filter)

    return render(request, 'electives/dept_dashboard.html', {
        'department': department,
        'courses': courses,
        'students': students_qs,
        'form': form,
        'total_seats': total_seats,
        'filled_seats': filled_seats,
        'remaining_seats': total_seats - filled_seats,
        'preferences': preferences,
        'tab': tab,
        'sem_filter': sem_filter,
        'section_filter': section_filter,
        'sem_choices': sem_choices,
        'section_choices': section_choices,
        'total_students': all_students.count(),
    })


# ── Main Admin Dashboard ───────────────────────────────────────────────────────
def main_admin_dashboard(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect('login')

    all_courses = Course.objects.select_related('department').order_by('semester', 'category', 'department__name', 'name')
    departments = Department.objects.all()

    # Student filters
    dept_f    = request.GET.get('dept_f', '')
    sem_f     = request.GET.get('sem_f', '')
    section_f = request.GET.get('section_f', '')

    all_students_qs = Student.objects.select_related('department')
    students = all_students_qs.order_by('department', 'current_semester', 'usn')
    if dept_f:
        students = students.filter(department__name=dept_f)
    if sem_f:
        students = students.filter(current_semester=sem_f)
    if section_f:
        students = students.filter(section=section_f)

    student_sem_choices     = sorted(set(all_students_qs.values_list('current_semester', flat=True)))
    student_section_choices = sorted(set(all_students_qs.values_list('section', flat=True)))

    semesters = sorted(set(all_courses.values_list('semester', flat=True)))

    # Build grouped structure: { sem: { category_label: { courses, count, published_count } } }
    from collections import OrderedDict
    CAT_LABEL = dict(CATEGORY_CHOICES)
    groups = OrderedDict()
    for sem in semesters:
        groups[sem] = OrderedDict()
        for cat_key, cat_label in CATEGORY_CHOICES:
            qs = all_courses.filter(semester=sem, category=cat_key)
            if qs.exists():
                groups[sem][cat_key] = {
                    'label':           cat_label,
                    'courses':         list(qs),
                    'total':           qs.count(),
                    'published':       qs.filter(is_published=True).count(),
                    'all_published':   qs.filter(is_published=True).count() == qs.count(),
                    'none_published':  qs.filter(is_published=True).count() == 0,
                }

    tab = request.GET.get('tab', 'courses')

    # Allocation filters
    alloc_dept = request.GET.get('alloc_dept', '')
    alloc_category = request.GET.get('alloc_category', '')
    alloc_sem = request.GET.get('alloc_sem', '')
    alloc_status = request.GET.get('alloc_status', '')
    
    # Filter all_preferences based on allocation filters
    all_preferences = Preference.objects.select_related(
        'student', 'student__department', 'course', 'course__department'
    ).order_by('timestamp')
    
    if alloc_dept:
        all_preferences = all_preferences.filter(course__department__name=alloc_dept)
    if alloc_category:
        all_preferences = all_preferences.filter(course__category=alloc_category)
    if alloc_sem:
        all_preferences = all_preferences.filter(course__semester=alloc_sem)
    if alloc_status:
        all_preferences = all_preferences.filter(status=alloc_status)

    return render(request, 'electives/main_admin.html', {
        'groups':            groups,
        'departments':       departments,
        'semesters':         semesters,
        'students':          students,
        'tab':               tab,
        'dept_f':            dept_f,
        'sem_f':             sem_f,
        'section_f':         section_f,
        'student_sem_choices':     student_sem_choices,
        'student_section_choices': student_section_choices,
        'total_students':    Student.objects.count(),
        'total_courses':     all_courses.count(),
        'published_courses': all_courses.filter(is_published=True).count(),
        'total_allocations': Preference.objects.filter(status='allocated').count(),
        'all_preferences':   all_preferences,
        'category_choices':  CATEGORY_CHOICES,
    })


def upload_students(request):
    """Upload students via CSV: USN, Name, Department, Semester, Section, Class, CGPA"""
    if not request.user.is_superuser:
        return redirect('login')

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))

        created = 0
        updated = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            try:
                usn      = row.get('USN', '').strip()
                name     = row.get('Name', '').strip()
                dept_name= row.get('Department', '').strip()
                sem      = int(row.get('Semester', 1))
                section  = row.get('Section', 'A').strip()
                cgpa_val = float(row.get('CGPA', 0.0))

                if not usn or not name or not dept_name:
                    errors.append(f"Row {i}: USN, Name, Department are required.")
                    continue

                dept, _ = Department.objects.get_or_create(name=dept_name)

                # Create or update Django User
                user, user_created = User.objects.get_or_create(username=usn)
                if user_created:
                    user.set_password('student@1234')
                    user.save()

                # Create or update Student
                student, s_created = Student.objects.update_or_create(
                    usn=usn,
                    defaults={
                        'name': name,
                        'department': dept,
                        'current_semester': sem,
                        'section': section,
                        'user': user,
                        'must_change_password': True,
                    }
                )

                # Save CGPA as StudentSemester record
                if cgpa_val > 0:
                    StudentSemester.objects.update_or_create(
                        student=student, semester=sem,
                        defaults={'cgpa': cgpa_val}
                    )

                if s_created:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")

        msg = f"Upload complete — {created} created, {updated} updated."
        if errors:
            msg += f" {len(errors)} error(s): " + "; ".join(errors[:3])
            messages.warning(request, msg)
        else:
            messages.success(request, msg)

    return redirect('/admin-panel/?tab=students')


def delete_student(request, student_id):
    if not request.user.is_superuser:
        return redirect('login')
    student = get_object_or_404(Student, id=student_id)
    name = student.name
    
    # Get all allocated preferences for this student before deletion
    allocated_prefs = Preference.objects.filter(student=student, status='allocated').select_related('course')
    
    # Store course info for waitlist promotion
    courses_to_promote = []
    for pref in allocated_prefs:
        courses_to_promote.append(pref.course)
    
    # Delete student (this will cascade delete preferences)
    if student.user:
        student.user.delete()
    else:
        student.delete()
    
    # Restore seats and promote waitlist for each course
    promoted_students = []
    for course in courses_to_promote:
        course.available_seats += 1
        course.save()
        
        # Try to promote next student from waitlist
        promoted_student = promote_waitlist(course)
        if promoted_student:
            promoted_students.append(f"{promoted_student.name} ({promoted_student.usn}) → {course.name}")
    
    # Create success message
    if promoted_students:
        promotion_msg = " | Waitlist promotions: " + ", ".join(promoted_students)
        messages.success(request, f"Student '{name}' removed.{promotion_msg}")
    else:
        messages.success(request, f"Student '{name}' removed.")
    
    return redirect('/admin-panel/?tab=students')


def dept_upload_students(request):
    """Department admin uploads their own students via CSV."""
    if not request.user.is_authenticated:
        return redirect('login')

    department = get_object_or_404(Department, user=request.user)

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))

        created = updated = 0
        errors = []

        for i, row in enumerate(reader, start=2):
            try:
                usn      = row.get('USN', '').strip()
                name     = row.get('Name', '').strip()
                sem      = int(row.get('Semester', 1))
                section  = row.get('Section', 'A').strip()
                cgpa_val = float(row.get('CGPA', 0.0))

                if not usn or not name:
                    errors.append(f"Row {i}: USN and Name are required.")
                    continue

                user, user_created = User.objects.get_or_create(username=usn)
                if user_created:
                    user.set_password('student@1234')
                    user.save()

                student, s_created = Student.objects.update_or_create(
                    usn=usn,
                    defaults={
                        'name': name,
                        'department': department,
                        'current_semester': sem,
                        'section': section,
                        'user': user,
                        'must_change_password': True,
                    }
                )

                if cgpa_val > 0:
                    StudentSemester.objects.update_or_create(
                        student=student, semester=sem,
                        defaults={'cgpa': cgpa_val}
                    )

                if s_created:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                errors.append(f"Row {i}: {str(e)}")

        msg = f"Upload done — {created} added, {updated} updated."
        if errors:
            msg += " Errors: " + "; ".join(errors[:3])
            messages.warning(request, msg)
        else:
            messages.success(request, msg)

    return redirect('/dashboard/?tab=students')


def dept_delete_student(request, student_id):
    """Department admin removes a student from their dept."""
    if not request.user.is_authenticated:
        return redirect('login')
    department = get_object_or_404(Department, user=request.user)
    student = get_object_or_404(Student, id=student_id, department=department)
    name = student.name
    
    # Get all allocated preferences for this student before deletion
    allocated_prefs = Preference.objects.filter(student=student, status='allocated').select_related('course')
    
    # Store course info for waitlist promotion
    courses_to_promote = []
    for pref in allocated_prefs:
        courses_to_promote.append(pref.course)
    
    # Delete student (this will cascade delete preferences)
    if student.user:
        student.user.delete()
    else:
        student.delete()
    
    # Restore seats and promote waitlist for each course
    promoted_students = []
    for course in courses_to_promote:
        course.available_seats += 1
        course.save()
        
        # Try to promote next student from waitlist
        promoted_student = promote_waitlist(course)
        if promoted_student:
            promoted_students.append(f"{promoted_student.name} ({promoted_student.usn}) → {course.name}")
    
    # Create success message
    if promoted_students:
        promotion_msg = " | Waitlist promotions: " + ", ".join(promoted_students)
        messages.success(request, f"'{name}' removed.{promotion_msg}")
    else:
        messages.success(request, f"'{name}' removed.")
    
    return redirect('/dashboard/?tab=students')


def dept_delete_course(request, course_id):
    """Department admin removes one of their own courses (only if unpublished)."""
    if not request.user.is_authenticated:
        return redirect('login')
    department = get_object_or_404(Department, user=request.user)
    course = get_object_or_404(Course, id=course_id, department=department)
    if course.is_published:
        messages.error(request, f"Cannot remove '{course.name}' — it is already published. Ask the main admin to unpublish it first.")
        return redirect('/dashboard/?tab=courses')
    name = course.name
    course.delete()
    messages.success(request, f"Course '{name}' removed.")
    return redirect('/dashboard/?tab=courses')


# ── Edit Course (Department Admin) ────────────────────────────────────────────
def dept_edit_course(request, course_id):
    """Department admin can edit their own courses (published or not)."""
    if not request.user.is_authenticated:
        return redirect('login')

    department = get_object_or_404(Department, user=request.user)
    course = get_object_or_404(Course, id=course_id, department=department)

    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            updated = form.save(commit=False)
            # Keep available_seats in sync if total seats changed
            seat_diff = updated.seats - course.seats
            updated.available_seats = max(0, course.available_seats + seat_diff)
            updated.save()
            messages.success(request, f"✅ Course '{updated.name}' updated successfully.")
            return redirect('/dashboard/?tab=courses')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = CourseForm(instance=course)

    return render(request, 'electives/edit_course.html', {
        'form': form,
        'course': course,
        'back_url': '/dashboard/?tab=courses',
        'is_dept': True,
    })


def dept_bulk_delete_students(request):
    """Department admin bulk-deletes students matching current filter."""
    if not request.user.is_authenticated:
        return redirect('login')
    department = get_object_or_404(Department, user=request.user)

    if request.method == 'POST':
        sem     = request.POST.get('sem', '')
        section = request.POST.get('section', '')
        ids     = request.POST.getlist('student_ids')
        remove_all = request.POST.get('remove_all', '')

        if ids and not remove_all:
            # Delete only checked rows
            qs = Student.objects.filter(id__in=ids, department=department)
        else:
            # Delete all matching filter
            qs = Student.objects.filter(department=department)
            if sem:
                qs = qs.filter(current_semester=sem)
            if section:
                qs = qs.filter(section=section)

        # Get all allocated preferences for students to be deleted
        allocated_prefs = Preference.objects.filter(
            student__in=qs, 
            status='allocated'
        ).select_related('course')
        
        # Store course info for waitlist promotion
        courses_to_promote = {}
        for pref in allocated_prefs:
            course = pref.course
            if course.id not in courses_to_promote:
                courses_to_promote[course.id] = course
        
        count = qs.count()
        from django.contrib.auth.models import User as AuthUser
        user_ids = list(qs.values_list('user_id', flat=True))
        AuthUser.objects.filter(id__in=[u for u in user_ids if u]).delete()
        qs.delete()
        
        # Restore seats and promote waitlist for each affected course
        total_promotions = 0
        for course in courses_to_promote.values():
            # Count how many seats were freed for this course
            freed_seats = allocated_prefs.filter(course=course).count()
            course.available_seats += freed_seats
            course.save()
            
            # Promote waitlist students
            for _ in range(freed_seats):
                promoted_student = promote_waitlist(course)
                if promoted_student:
                    total_promotions += 1
        
        if total_promotions > 0:
            messages.success(request, f"Removed {count} student(s). {total_promotions} waitlist student(s) automatically promoted.")
        else:
            messages.success(request, f"Removed {count} student(s).")

    # Preserve filters in redirect
    sem     = request.POST.get('sem', '')
    section = request.POST.get('section', '')
    qs_str  = f"tab=students{'&sem='+sem if sem else ''}{'&section='+section if section else ''}"
    return redirect(f'/dashboard/?{qs_str}')


def publish_course(request, course_id):
    if not request.user.is_superuser:
        return redirect('login')
    course = get_object_or_404(Course, id=course_id)
    course.is_published = True
    course.save()
    messages.success(request, f"'{course.name}' published.")
    return redirect('/admin-panel/?tab=courses')


def unpublish_course(request, course_id):
    if not request.user.is_superuser:
        return redirect('login')
    course = get_object_or_404(Course, id=course_id)
    course.is_published = False
    course.save()
    messages.warning(request, f"'{course.name}' unpublished.")
    return redirect('/admin-panel/?tab=courses')


def delete_course(request, course_id):
    if not request.user.is_superuser:
        return redirect('login')
    course = get_object_or_404(Course, id=course_id)
    name = course.name
    course.delete()
    messages.error(request, f"Course '{name}' has been deleted.")
    return redirect('/admin-panel/?tab=courses')


# ── Edit Course (Main Admin) ───────────────────────────────────────────────────
def edit_course(request, course_id):
    """Main admin can edit any course details (name, seats, credits, etc.)"""
    if not request.user.is_superuser:
        return redirect('login')

    course = get_object_or_404(Course, id=course_id)

    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            updated = form.save(commit=False)
            # Keep available_seats in sync if total seats changed
            seat_diff = updated.seats - course.seats
            updated.available_seats = max(0, course.available_seats + seat_diff)
            updated.save()
            messages.success(request, f"✅ Course '{updated.name}' updated successfully.")
            return redirect('/admin-panel/?tab=courses')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = CourseForm(instance=course)

    return render(request, 'electives/edit_course.html', {
        'form': form,
        'course': course,
    })


# ── Override Panel ─────────────────────────────────────────────────────────────
def override_panel(request):
    """Admin searches a student by USN and manages their allocations."""
    if not request.user.is_superuser:
        return redirect('login')

    usn = request.GET.get('usn', '').strip()
    student = None
    preferences = []
    available_courses = []

    if usn:
        student = Student.objects.filter(usn__iexact=usn).select_related('department').first()
        if student:
            preferences = Preference.objects.filter(student=student).select_related('course__department').order_by('rank')
            # Courses not already in student's preferences
            taken_ids = preferences.values_list('course_id', flat=True)
            all_available = Course.objects.filter(
                is_published=True,
                semester=student.current_semester
            ).exclude(id__in=taken_ids).select_related('department').order_by('semester', 'name')

            from .utils import is_same_dept_group
            available_courses = []
            for c in all_available:
                if c.category == 'open':
                    # Open: exclude same group
                    if not is_same_dept_group(student.department.name, c.department.name):
                        available_courses.append(c)
                else:
                    # Professional & Ability: only own department
                    if c.department_id == student.department_id:
                        available_courses.append(c)

    return render(request, 'electives/override.html', {
        'usn': usn,
        'student': student,
        'preferences': preferences,
        'available_courses': available_courses,
    })


def override_cancel(request, pref_id):
    """Admin cancels a student's preference and restores the seat."""
    if not request.user.is_superuser:
        return redirect('login')
    pref = get_object_or_404(Preference, id=pref_id)
    usn = pref.student.usn
    course = pref.course
    
    # Restore seat if it was allocated
    if pref.status == 'allocated':
        course.available_seats += 1
        course.save()
        
        # Try to promote next student from waitlist
        promoted_student = promote_waitlist(course)
        if promoted_student:
            messages.success(request, f"Preference for '{course.name}' cancelled. Seat automatically allocated to {promoted_student.name} ({promoted_student.usn}) from waitlist.")
        else:
            messages.success(request, f"Preference for '{course.name}' cancelled and seat restored.")
    else:
        messages.success(request, f"Preference for '{course.name}' cancelled.")
    
    pref.delete()
    
    # Re-number remaining ranks
    for i, p in enumerate(Preference.objects.filter(student=pref.student).order_by('rank'), start=1):
        p.rank = i
        p.save()
    
    return redirect(f'/override/?usn={usn}')


def override_force_allocate(request):
    """Admin force-allocates a specific course to a student."""
    if not request.user.is_superuser:
        return redirect('login')
    if request.method != 'POST':
        return redirect('override_panel')

    usn       = request.POST.get('usn', '').strip()
    course_id = request.POST.get('course_id', '')
    student   = get_object_or_404(Student, usn__iexact=usn)
    course    = get_object_or_404(Course, id=course_id)

    # Already has this course?
    if Preference.objects.filter(student=student, course=course).exists():
        messages.warning(request, f"{student.usn} already has '{course.name}' in their preferences.")
        return redirect(f'/override/?usn={usn}')

    # Check department group restriction
    from .utils import is_same_dept_group
    if course.category == 'open':
        if is_same_dept_group(student.department.name, course.department.name):
            messages.error(request, f"❌ Cannot allocate '{course.name}' to {student.name} ({student.usn}). Open Electives cannot be from the student's own department group ({student.department.name} → {course.department.name}).")
            return redirect(f'/override/?usn={usn}')
    elif course.category in ('professional', 'ability'):
        if course.department_id != student.department_id:
            cat_label = course.get_category_display()
            messages.error(request, f"❌ Cannot allocate '{course.name}' to {student.name} ({student.usn}). {cat_label} courses must be from the student's own department ({student.department.name}).")
            return redirect(f'/override/?usn={usn}')

    rank = Preference.objects.filter(student=student).count() + 1

    # Force allocate — bypass seat check (admin override)
    Preference.objects.create(
        student=student,
        course=course,
        rank=rank,
        status='allocated'
    )
    # Decrement seat only if available
    if course.available_seats > 0:
        course.available_seats -= 1
        course.save()

    messages.success(request, f"✅ Force-allocated '{course.name}' to {student.name} ({student.usn}).")
    return redirect(f'/override/?usn={usn}')


def bulk_publish(request):
    """Publish all courses matching semester + category in one click."""
    if not request.user.is_superuser:
        return redirect('login')
    sem      = request.GET.get('sem', '')
    category = request.GET.get('category', '')
    action   = request.GET.get('action', 'publish')   # publish | unpublish
    qs = Course.objects.all()
    if sem:
        qs = qs.filter(semester=sem)
    if category:
        qs = qs.filter(category=category)
    count = qs.count()
    if action == 'unpublish':
        qs.update(is_published=False)
        messages.warning(request, f"Unpublished {count} course(s) — Sem {sem} · {category or 'all categories'}.")
    else:
        qs.update(is_published=True)
        messages.success(request, f"Published {count} course(s) — Sem {sem} · {category or 'all categories'}.")
    return redirect('/admin-panel/?tab=courses')


# ── Student Dashboard ──────────────────────────────────────────────────────────
def student_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('student_login')

    student = get_object_or_404(Student, user=request.user)

    if student.must_change_password:
        return redirect('change_password')

    category = request.GET.get('category', '')

    from .utils import is_same_dept_group

    # Base: only published courses for student's current semester
    base_qs = Course.objects.filter(
        is_published=True,
        semester=student.current_semester
    ).select_related('department')

    # ── VISIBILITY RULES ──────────────────────────────────────────────────────
    # Open Elective   → show ALL departments (student sees all, but same-group is blocked)
    # Professional    → show ONLY student's own department
    # Ability         → show ONLY student's own department

    open_courses = base_qs.filter(category='open').order_by('department__name', 'name')
    own_dept_courses = base_qs.filter(
        category__in=['professional', 'ability'],
        department=student.department
    ).order_by('category', 'name')

    # Combine and sort: own dept first, then open electives by dept
    courses = list(own_dept_courses) + list(open_courses)

    # Mark same-group flag (only relevant for open electives)
    for course in courses:
        if course.category == 'open':
            course.is_same_group = is_same_dept_group(student.department.name, course.department.name)
        else:
            course.is_same_group = False  # Professional & Ability: always own dept, always eligible

    if category:
        courses = [c for c in courses if c.category == category]

    # Re-sort by department name for {% regroup %} to work correctly
    courses.sort(key=lambda c: (c.department.name, c.category, c.name))

    preferences = Preference.objects.filter(student=student).select_related('course')
    selected_ids = set(p.course_id for p in preferences)

    return render(request, 'electives/student_dashboard.html', {
        'student': student,
        'courses': courses,
        'preferences': preferences,
        'selected_ids': selected_ids,
        'category_choices': CATEGORY_CHOICES,
        'selected_category': category,
    })


# ── Submit Preference ──────────────────────────────────────────────────────────
def submit_preference(request, course_id):
    if not request.user.is_authenticated:
        return redirect('student_login')

    student = get_object_or_404(Student, user=request.user)
    course = get_object_or_404(Course, id=course_id)

    if Preference.objects.filter(student=student).count() >= 9:
        messages.error(request, "You can submit at most 9 preferences (3 per category: Open, Professional, Ability).")
        return redirect('student_dashboard')

    if Preference.objects.filter(student=student, course=course).exists():
        messages.error(request, "You already added this course.")
        return redirect('student_dashboard')

    eligible, msg = check_eligibility(student, course)
    if not eligible:
        messages.error(request, msg)
        return redirect('student_dashboard')

    rank = Preference.objects.filter(student=student).count() + 1

    if course.available_seats > 0:
        status = 'allocated'
        course.available_seats -= 1
        course.save()
        messages.success(request, f"✅ Allocated to {course.name}!")
    else:
        status = 'pending'  # Changed from 'rejected' to 'pending' for waitlist
        messages.warning(request, f"⏳ Added to waitlist for {course.name}. You'll be allocated if seats become available.")

    Preference.objects.create(student=student, course=course, rank=rank, status=status)

    return redirect('results')


# ── Results ────────────────────────────────────────────────────────────────────
def results(request):
    if not request.user.is_authenticated:
        return redirect('student_login')
    student = get_object_or_404(Student, user=request.user)
    preferences = Preference.objects.filter(student=student).select_related('course__department')
    return render(request, 'electives/results.html', {
        'student': student,
        'preferences': preferences,
    })


# ── AJAX Seat Counter ──────────────────────────────────────────────────────────
def get_seats(request):
    data = list(Course.objects.values('id', 'available_seats', 'seats'))
    return JsonResponse(data, safe=False)


# ── Run Allocation ─────────────────────────────────────────────────────────────
def run_allocation(request):
    if not request.user.is_superuser:
        return redirect('login')
    
    # First run the standard allocation
    allocate_electives()
    
    # Then auto-allocate any remaining pending preferences if seats are available
    promoted_count = auto_allocate_pending()
    
    if promoted_count > 0:
        messages.success(request, f"FCFS Allocation completed. {promoted_count} additional students promoted from waitlist.")
    else:
        messages.success(request, "FCFS Allocation completed.")
    
    return redirect('main_admin')


# ── CSV Export ─────────────────────────────────────────────────────────────────
def export_csv(request):
    if not request.user.is_authenticated:
        return redirect('login')

    qs = Preference.objects.select_related(
        'student', 'student__department',
        'course', 'course__department'
    )

    dept = request.GET.get('department', '')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')
    sem = request.GET.get('sem', '')

    if dept:
        qs = qs.filter(course__department__name__icontains=dept)
    if category:
        qs = qs.filter(course__category=category)
    if status:
        qs = qs.filter(status=status)
    if sem:
        qs = qs.filter(course__semester=sem)

    # Build a descriptive filename
    parts = ['allocation']
    if sem:      parts.append(f'sem{sem}')
    if category: parts.append(category)
    if status:   parts.append(status)
    if dept:     parts.append(dept.replace(' ', '_'))
    filename = '_'.join(parts) + '.csv'

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['USN', 'Student Name', 'Student Dept', 'Course', 'Course Dept',
                     'Category', 'Semester', 'Credits', 'Rank', 'Status', 'CGPA', 'Timestamp'])

    for p in qs:
        writer.writerow([
            p.student.usn,
            p.student.name,
            p.student.department.name,
            p.course.name,
            p.course.department.name,
            p.course.get_category_display(),
            p.course.semester,
            p.course.credits,
            p.rank,
            p.status,
            get_latest_cgpa(p.student),
            p.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        ])

    return response


# ── Catalog (public) ───────────────────────────────────────────────────────────
def catalog(request):
    from collections import OrderedDict

    category_filter = request.GET.get('category', '')

    # Order: semester ASC, then category in fixed order: ability → open → professional
    CATEGORY_ORDER = {'ability': 0, 'open': 1, 'professional': 2}

    qs = Course.objects.filter(is_published=True).select_related('department')
    if category_filter:
        qs = qs.filter(category=category_filter)

    # Sort in Python: primary = semester, secondary = category order, tertiary = name
    courses_sorted = sorted(
        qs,
        key=lambda c: (c.semester, CATEGORY_ORDER.get(c.category, 9), c.name)
    )

    # Build grouped structure: { semester: { category_key: [courses] } }
    # Used by template to render sections in the right order
    grouped = OrderedDict()
    for course in courses_sorted:
        sem = course.semester
        cat = course.category
        if sem not in grouped:
            grouped[sem] = OrderedDict()
        if cat not in grouped[sem]:
            grouped[sem][cat] = []
        grouped[sem][cat].append(course)

    return render(request, 'electives/catalog.html', {
        'courses': courses_sorted,          # flat list (used when category filter active)
        'grouped': grouped,                 # nested dict for full grouped view
        'category_choices': CATEGORY_CHOICES,
        'selected_category': category_filter,
    })


# ── Download Student CSV Template ─────────────────────────────────────────────
def download_student_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Download Template.csv"'
    writer = csv.writer(response)
    writer.writerow(['USN', 'Name', 'Semester', 'Section', 'CGPA'])
    writer.writerow(['1JB23CS001', 'Rahul Sharma', '5', 'A', '8.5'])
    writer.writerow(['1JB23CS002', 'Priya Nair',   '5', 'B', '7.2'])
    writer.writerow(['1JB23CS003', 'Arjun Mehta',  '6', 'A', '9.1'])
    writer.writerow(['1JB23CS004', 'Sneha Rao',    '6', 'B', '6.8'])
    return response


# ── Export Students CSV ────────────────────────────────────────────────────────
def export_students(request):
    if not request.user.is_authenticated:
        return redirect('login')
    qs = Student.objects.select_related('department').order_by('current_semester', 'section', 'usn')
    dept    = request.GET.get('dept', '')
    sem     = request.GET.get('sem', '')
    section = request.GET.get('section', '')
    if dept:
        qs = qs.filter(department__name=dept)
    if sem:
        qs = qs.filter(current_semester=sem)
    if section:
        qs = qs.filter(section=section)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="students.csv"'
    writer = csv.writer(response)
    writer.writerow(['USN', 'Name', 'Department', 'Semester', 'Section', 'CGPA'])
    for s in qs:
        writer.writerow([s.usn, s.name, s.department.name, s.current_semester, s.section, s.cgpa()])
    return response


# ── Download Courses Group-wise ────────────────────────────────────────────────
def download_courses_groupwise(request):
    """Download courses organized by department and category"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    courses = Course.objects.filter(is_published=True).select_related('department').order_by(
        'department__name', 'category', 'semester', 'name'
    )
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="courses_groupwise.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Department', 'Category', 'Course Name', 'Semester', 'Credits', 
        'Total Seats', 'Available Seats', 'Filled Seats', 'Prerequisites'
    ])
    
    for course in courses:
        filled_seats = course.seats - course.available_seats
        writer.writerow([
            course.department.name,
            course.get_category_display(),
            course.name,
            course.semester,
            course.credits,
            course.seats,
            course.available_seats,
            filled_seats,
            course.prerequisites or 'None'
        ])
    
    return response


# ── Download Allocation Details with Filters ───────────────────────────────────
def download_allocation_details(request):
    """Download allocation details with filtering options"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Get filter parameters
    subject_filter = request.GET.get('subject', '')
    class_filter = request.GET.get('class', '')
    sem_filter = request.GET.get('sem', '')
    dept_filter = request.GET.get('dept', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    download_all = request.GET.get('download', '') == 'all'
    
    # If no filters provided and not download_all, show filter form
    if not download_all and not any([subject_filter, class_filter, sem_filter, dept_filter, category_filter, status_filter]):
        # Get filter options
        departments = Department.objects.all().order_by('name')
        semesters = sorted(set(Course.objects.values_list('semester', flat=True)))
        sections = sorted(set(Student.objects.values_list('section', flat=True)))
        courses = Course.objects.filter(is_published=True).order_by('name')
        
        return render(request, 'electives/download_filters.html', {
            'departments': departments,
            'semesters': semesters,
            'sections': sections,
            'courses': courses,
            'category_choices': CATEGORY_CHOICES,
        })
    
    # Apply filters to preferences
    qs = Preference.objects.select_related(
        'student', 'student__department', 'course', 'course__department'
    ).order_by('course__department__name', 'course__name', 'student__usn')
    
    if subject_filter:
        qs = qs.filter(course__name__icontains=subject_filter)
    if class_filter:
        qs = qs.filter(student__section=class_filter)
    if sem_filter:
        qs = qs.filter(course__semester=sem_filter)
    if dept_filter:
        qs = qs.filter(course__department__name=dept_filter)
    if category_filter:
        qs = qs.filter(course__category=category_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    
    # Build filename based on filters
    filename_parts = ['allocation_details']
    if download_all:
        filename_parts.append('all')
    else:
        if dept_filter:
            filename_parts.append(f'dept_{dept_filter.replace(" ", "_")}')
        if sem_filter:
            filename_parts.append(f'sem_{sem_filter}')
        if category_filter:
            filename_parts.append(f'cat_{category_filter}')
        if class_filter:
            filename_parts.append(f'class_{class_filter}')
        if status_filter:
            filename_parts.append(f'status_{status_filter}')
    
    filename = '_'.join(filename_parts) + '.csv'
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        'USN', 'Student Name', 'Student Department', 'Student Semester', 'Section',
        'Course Name', 'Course Department', 'Category', 'Course Semester', 'Credits',
        'Preference Rank', 'Status', 'CGPA', 'Timestamp'
    ])
    
    for pref in qs:
        writer.writerow([
            pref.student.usn,
            pref.student.name,
            pref.student.department.name,
            pref.student.current_semester,
            pref.student.section,
            pref.course.name,
            pref.course.department.name,
            pref.course.get_category_display(),
            pref.course.semester,
            pref.course.credits,
            pref.rank,
            pref.status.title(),
            get_latest_cgpa(pref.student),
            pref.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response

# ── Download Course-specific Students ──────────────────────────────────────────
def download_course_students(request, course_id):
    """Download students list for a specific course"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions - only admin or course department can download
    if not request.user.is_superuser:
        department = get_object_or_404(Department, user=request.user)
        if course.department != department:
            messages.error(request, "You can only download students for your department's courses.")
            return redirect('dashboard')
    
    preferences = Preference.objects.filter(course=course).select_related(
        'student', 'student__department'
    ).order_by('rank', 'timestamp')
    
    filename = f"{course.name.replace(' ', '_')}_students.csv"
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        'USN', 'Student Name', 'Student Department', 'Student Semester', 'Section',
        'CGPA', 'Preference Rank', 'Status', 'Timestamp'
    ])
    
    for pref in preferences:
        writer.writerow([
            pref.student.usn,
            pref.student.name,
            pref.student.department.name,
            pref.student.current_semester,
            pref.student.section,
            get_latest_cgpa(pref.student),
            pref.rank,
            pref.status.title(),
            pref.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response


# ── Edit Profile (Student) ─────────────────────────────────────────────────────
def edit_student_profile(request):
    """Student can edit their name and password"""
    if not request.user.is_authenticated:
        return redirect('student_login')
    
    student = get_object_or_404(Student, user=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_name':
            new_name = request.POST.get('name', '').strip()
            if not new_name:
                messages.error(request, "Name cannot be empty.")
            else:
                student.name = new_name
                student.save()
                messages.success(request, "Name updated successfully!")
                return redirect('edit_student_profile')
        
        elif action == 'update_password':
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
            elif len(new_password) < 4:
                messages.error(request, "New password must be at least 4 characters.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                messages.success(request, "Password updated successfully! Please log in again.")
                return redirect('student_login')
    
    return render(request, 'electives/edit_student_profile.html', {
        'student': student,
    })


# ── Edit Profile (Admin/Department) ────────────────────────────────────────────
def edit_admin_profile(request):
    """Admin/Department user can edit their username and password"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Check if user is admin or department
    is_superuser = request.user.is_superuser
    department = None
    if not is_superuser:
        try:
            department = Department.objects.get(user=request.user)
        except Department.DoesNotExist:
            messages.error(request, "Access denied.")
            return redirect('home')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_username':
            new_username = request.POST.get('username', '').strip()
            if not new_username:
                messages.error(request, "Username cannot be empty.")
            elif User.objects.filter(username=new_username).exclude(id=request.user.id).exists():
                messages.error(request, "Username already taken.")
            else:
                request.user.username = new_username
                request.user.save()
                messages.success(request, "Username updated successfully!")
                return redirect('edit_admin_profile')
        
        elif action == 'update_password':
            current_password = request.POST.get('current_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            
            if not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
            elif len(new_password) < 4:
                messages.error(request, "New password must be at least 4 characters.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                messages.success(request, "Password updated successfully! Please log in again.")
                return redirect('login')
    
    return render(request, 'electives/edit_admin_profile.html', {
        'is_superuser': is_superuser,
        'department': department,
    })


# ── Admin Edit Any Profile ─────────────────────────────────────────────────────
def admin_edit_profile(request):
    """Super admin can edit any user's profile by username"""
    if not request.user.is_superuser:
        return redirect('login')
    
    username = request.GET.get('username', '').strip()
    target_user = None
    target_student = None
    target_department = None
    
    if username:
        try:
            target_user = User.objects.get(username=username)
            # Check if it's a student
            try:
                target_student = Student.objects.get(user=target_user)
            except Student.DoesNotExist:
                pass
            # Check if it's a department admin
            try:
                target_department = Department.objects.get(user=target_user)
            except Department.DoesNotExist:
                pass
        except User.DoesNotExist:
            messages.error(request, f"User '{username}' not found.")
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if not target_user:
            messages.error(request, "No user selected.")
            return redirect('admin_edit_profile')
        
        if action == 'update_username':
            new_username = request.POST.get('username', '').strip()
            if not new_username:
                messages.error(request, "Username cannot be empty.")
            elif User.objects.filter(username=new_username).exclude(id=target_user.id).exists():
                messages.error(request, "Username already taken.")
            else:
                target_user.username = new_username
                target_user.save()
                messages.success(request, f"Username updated to '{new_username}' successfully!")
                return redirect(f'/admin-edit-profile/?username={new_username}')
        
        elif action == 'update_name' and target_student:
            new_name = request.POST.get('name', '').strip()
            if not new_name:
                messages.error(request, "Name cannot be empty.")
            else:
                target_student.name = new_name
                target_student.save()
                messages.success(request, f"Student name updated to '{new_name}' successfully!")
                return redirect(f'/admin-edit-profile/?username={target_user.username}')
        
        elif action == 'reset_password':
            new_password = request.POST.get('new_password', '')
            if len(new_password) < 4:
                messages.error(request, "Password must be at least 4 characters.")
            else:
                target_user.set_password(new_password)
                target_user.save()
                # Reset must_change_password for students
                if target_student:
                    target_student.must_change_password = True
                    target_student.save()
                messages.success(request, f"Password reset successfully for '{target_user.username}'!")
                return redirect(f'/admin-edit-profile/?username={target_user.username}')
    
    return render(request, 'electives/admin_edit_profile.html', {
        'username': username,
        'target_user': target_user,
        'target_student': target_student,
        'target_department': target_department,
    })