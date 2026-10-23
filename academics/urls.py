from django.urls import path
from . import views

app_name = "academics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    # المعلم
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/sessions/new/", views.teacher_session_create, name="teacher_session_create"),
    path("teacher/sessions/<int:pk>/edit/", views.teacher_session_edit, name="teacher_session_edit"),
    path("teacher/sessions/<int:pk>/submit/", views.teacher_session_submit, name="teacher_session_submit"),

    # مدير الدراسات
    path("director/", views.director_dashboard, name="director_dashboard"),
    path("director/assignments/new/", views.director_assignment_create, name="director_assignment_create"),
    path("director/sessions/<int:pk>/review/", views.director_session_review, name="director_session_review"),
    path("director/sessions/<int:pk>/edit/", views.director_session_edit, name="director_session_edit"),

    # السكرتير
    path("secretary/", views.secretary_dashboard, name="secretary_dashboard"),
    path("secretary/assignments/new/", views.secretary_assignment_create, name="secretary_assignment_create"),

    # العميد
    path("dean/", views.dean_dashboard, name="dean_dashboard"),

    # الأدمين
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/sessions/<int:pk>/delete/", views.admin_session_delete, name="admin_session_delete"),

    # المحاسب
    path("accountant/", views.accountant_dashboard, name="accountant_dashboard"),
    path("accountant/teachers/<int:teacher_id>/", views.accountant_teacher_detail, name="accountant_teacher_detail"),
    # الإشعارات
    path("notifications/", views.notifications_list, name="notifications_list"),
    path("notifications/<int:pk>/open/", views.notification_open, name="notification_open"),
    # Fiches de paie
    path("accountant/payslips/", views.accountant_payslips, name="accountant_payslips"),
    path("accountant/payslips/<int:pk>/paid/", views.accountant_payslip_mark_paid, name="accountant_payslip_mark_paid"),
    path("accountant/payslips/<int:pk>/pending/", views.accountant_payslip_mark_pending, name="accountant_payslip_mark_pending"),

    # Finances du doyen
    path("dean/finances/", views.dean_finances, name="dean_finances"),
    # Horaire hebdomadaire
    path("secretary/weekly/", views.secretary_weekly_list, name="secretary_weekly_list"),
    path("secretary/weekly/new/", views.secretary_weekly_create, name="secretary_weekly_create"),
    path("director/weekly/", views.director_weekly_list, name="director_weekly_list"),
    path("director/weekly/<int:pk>/delete/", views.director_weekly_delete, name="director_weekly_delete"),
    # Archive des horaires hebdomadaires
    path("weekly/archive/", views.weekly_archive, name="weekly_archive"),
    path("teacher/weekly/", views.teacher_weekly_schedule, name="teacher_weekly_schedule"),
]
