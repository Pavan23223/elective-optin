from .models import Student, Course, Preference, StudentCourseHistory, StudentSemester, DEPARTMENT_GROUPS


def get_latest_cgpa(student):
    latest = StudentSemester.objects.filter(student=student).order_by('-semester').first()
    return latest.cgpa if latest else 0.0


def is_same_dept_group(student_dept_name, course_dept_name):
    """
    Check if student and course departments are in the same group.
    Students cannot take courses from their own department group.
    Groups: IT (CSE/ISE/AIML/CSDS), Mechanical, Civil, EC/EEE
    """
    student_dept_upper = student_dept_name.upper()
    course_dept_upper = course_dept_name.upper()
    
    # Check each department group
    for group in DEPARTMENT_GROUPS:
        if student_dept_upper in group and course_dept_upper in group:
            return True
    
    # If not in any group, check exact match (same department)
    return student_dept_upper == course_dept_upper


def check_eligibility(student, course):
    """
    Check if student is eligible to take this course.

    RULES:
    1. Students can submit 3 preferences per category (total 9 preferences).
    2. Students will get allocated 1 course per category (total 3 courses).
    3. Open Elective   → visible from ALL departments, but CANNOT apply to own department group.
    4. Professional    → ONLY from student's own department.
    5. Ability         → ONLY from student's own department.
    6. Course must be for student's current semester.
    """

    # 1. Max 3 preferences per category
    existing_in_category_count = Preference.objects.filter(
        student=student,
        course__category=course.category
    ).count()

    if existing_in_category_count >= 3:
        category_name = dict(course._meta.get_field('category').choices).get(course.category, course.category)
        return False, f"You already have 3 {category_name} preferences. You can only submit 3 preferences per category."

    # 2. Open Elective: cannot be from same department group
    if course.category == 'open':
        if is_same_dept_group(student.department.name, course.department.name):
            return False, (
                f"Open Electives cannot be from your own department group. "
                f"You cannot take {course.department.name} courses as Open Elective."
            )

    # 3. Professional & Ability: MUST be from student's own department
    if course.category in ('professional', 'ability'):
        if course.department_id != student.department_id:
            category_name = dict(course._meta.get_field('category').choices).get(course.category, course.category)
            return False, (
                f"{category_name} courses must be from your own department ({student.department.name}). "
                f"You cannot take {course.department.name} courses as {category_name}."
            )

    # 4. Already studied this course
    if StudentCourseHistory.objects.filter(student=student, course_name=course.name).exists():
        return False, f"You have already completed '{course.name}'."

    # 5. Course semester must match student's current semester
    if course.semester != student.current_semester:
        return False, (
            f"'{course.name}' is offered in Semester {course.semester}, "
            f"but you are in Semester {student.current_semester}."
        )

    return True, "Eligible"


def allocate_electives():
    """
    FCFS allocation with category limits.
    Each student gets maximum 1 course per category (Open, Professional, Ability).
    Processes all pending preferences ordered by timestamp.
    """
    preferences = Preference.objects.filter(status='pending').order_by('timestamp')
    
    for pref in preferences:
        course = pref.course
        student = pref.student
        
        # Check if student already has an allocated course in this category
        already_allocated_in_category = Preference.objects.filter(
            student=student,
            course__category=course.category,
            status='allocated'
        ).exists()
        
        if already_allocated_in_category:
            # Student already has a course in this category, reject this preference
            pref.status = 'rejected'
            pref.save()
            continue
        
        # Try to allocate if seats available
        if course.available_seats > 0:
            pref.status = 'allocated'
            course.available_seats -= 1
            course.save()
        else:
            pref.status = 'rejected'  # No seats available
        
        pref.save()


def reset_allocation():
    for course in Course.objects.all():
        course.available_seats = course.seats
        course.save()
    Preference.objects.all().update(status='pending')


def promote_waitlist(course):
    """
    Automatically promote the next student from waitlist when a seat becomes available.
    Ensures student doesn't already have an allocated course in this category.
    """
    # Find pending preferences for this course (oldest first - FCFS)
    pending_prefs = Preference.objects.filter(
        course=course, 
        status='pending'
    ).select_related('student').order_by('timestamp')
    
    for next_waitlist in pending_prefs:
        if course.available_seats <= 0:
            break
            
        student = next_waitlist.student
        
        # Check if student already has an allocated course in this category
        already_allocated_in_category = Preference.objects.filter(
            student=student,
            course__category=course.category,
            status='allocated'
        ).exists()
        
        if already_allocated_in_category:
            # Student already has a course in this category, skip to next
            continue
        
        # Check if student is still eligible
        eligible, msg = check_eligibility(student, course)
        
        if eligible:
            # Promote from waitlist to allocated
            next_waitlist.status = 'allocated'
            next_waitlist.save()
            
            # Decrease available seats
            course.available_seats -= 1
            course.save()
            
            return student
    
    return None


def auto_allocate_pending():
    """
    Automatically allocate any pending preferences if seats become available.
    This should be called after any seat restoration.
    """
    # Get all courses that have both available seats and pending preferences
    courses_with_pending = Course.objects.filter(
        available_seats__gt=0,
        preference__status='pending'
    ).distinct()
    
    promoted_count = 0
    for course in courses_with_pending:
        # Keep promoting until no more seats or no more pending students
        while course.available_seats > 0:
            promoted_student = promote_waitlist(course)
            if promoted_student:
                promoted_count += 1
                # Refresh course object to get updated available_seats
                course.refresh_from_db()
            else:
                break
    
    return promoted_count
