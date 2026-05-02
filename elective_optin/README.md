# Priority-Based Elective Opt-In System

A Django web application for fair, transparent elective course allocation with constraint-based opting, real-time seat availability, and CSV reporting.

---

## Quick Start

```bash
cd elective_optin
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit: http://127.0.0.1:8000

---

## Features

- **Course Catalog** — Browse courses filtered by Professional Elective, Open Elective, or Ability Enhancement
- **College-Wide Open Electives** — Students across departments see all open electives in one view
- **Constraint-Based Opting** — Prevents opting for already-studied or future-scheduled courses; max 3 ranked preferences per student
- **First-Come-First-Serve Allocation** — Seats allocated by submission timestamp; overflow marked as rejected
- **Real-Time Seat Counter** — AJAX polling updates seat counts every 2 seconds without page refresh
- **CSV Export** — Download allocation report filtered by department, category, or status
- **Responsive UI** — Bootstrap 5 layout works on mobile and desktop

---

## URL Reference

| URL | Description |
|-----|-------------|
| `/` | Home — choose login type |
| `/catalog/` | Public course catalog with category filter |
| `/catalog/?category=open` | Filter by open electives |
| `/student-login/` | Student login |
| `/student-dashboard/` | Student course browser + apply |
| `/results/` | Student's ranked preferences + status |
| `/login/` | Department admin login |
| `/dashboard/` | Department admin dashboard |
| `/allocate/` | Trigger FCFS allocation (admin) |
| `/export/` | Download CSV report |
| `/export/?department=CSE&category=open&status=allocated` | Filtered CSV |
| `/get-seats/` | AJAX endpoint — returns JSON seat counts |

---

## CO–SDG Mapping

| Course Outcome | How This Project Demonstrates It | SDG Target Addressed |
|---|---|---|
| **CO1: MVT Architecture** | URL routing for catalog, preferences, allocation, and export endpoints using Django's URL dispatcher and view functions | SDG 4.3 — Equal access to technical education |
| **CO2: Models & Forms** | `Preference` model with rank + `StudentCourseHistory` constraint checking; `PreferenceForm` and `ExportFilterForm` with server-side validation | SDG 4.5 — Eliminate disparities in access |
| **CO3: Template Inheritance** | Reusable `base.html` with Bootstrap 5 navbar and messages; responsive catalog, dashboard, and results views using `{% extends %}` and `{% block %}` | SDG 10.2 — Empower marginalized groups through inclusive design |
| **CO4: Non-HTML Output** | CSV export via `HttpResponse(content_type='text/csv')` with filtered querysets by department, category, and status for transparent reporting | SDG 16.6 — Effective, accountable, and transparent institutions |
| **CO5: AJAX Integration** | Real-time seat counter polling `/get-seats/` every 2 seconds; eligibility feedback without page refresh | SDG 9.C — Universal access to ICT and digital infrastructure |

---

## SDG Justification

Our Priority-Based Elective Opt-In system advances **SDG 4: Quality Education** (Target 4.5) by implementing a transparent, constraint-aware allocation algorithm that ensures equitable access to specialized courses while preventing curriculum redundancy — students cannot opt for courses already studied or scheduled in future semesters. The college-wide open elective publishing (CO3) supports **SDG 10: Reduced Inequalities** (Target 10.2) by empowering students across all departments to access diverse learning opportunities through a unified interface. Built with Django's validated forms (CO2) and AJAX-driven eligibility checks (CO5), the system demonstrates responsive, user-centered design that reduces bias in academic opportunity distribution while promoting inclusive, future-ready skill development aligned with industry job perspectives.

---

## Verification Checklist

- [ ] `python manage.py runserver` → app loads at http://127.0.0.1:8000
- [ ] Course catalog displays with features + job perspectives; category filters work
- [ ] Student submits preference for eligible course → saves to DB with rank
- [ ] Attempt to opt for already-studied or future-scheduled course → shows error message
- [ ] AJAX seat counter updates live every 2 seconds
- [ ] Allocation logic runs via `/allocate/` → FCFS ordering respected
- [ ] Overflow student rejected with clear badge
- [ ] `/export/?category=open` → downloads valid CSV with all columns
- [ ] Mobile view: preference form usable on phone screen
- [ ] README contains CO-SDG table + justification paragraph
