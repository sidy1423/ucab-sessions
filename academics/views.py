"""عروض النظام حسب الدور مع التحقق الكامل من الصلاحيات."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from .forms import AssignmentForm, RejectForm, SessionEditForm, SessionForm
from .models import Session, TeachingAssignment
from .services import (
    SessionLockedError,
    WorkflowError,
    approve_session,
    compute_all_teachers_hours,
    compute_all_teachers_salaries,
    compute_levels_grand_total,
    compute_levels_summary,
    compute_levels_totals,
    compute_teacher_hours,
    compute_teacher_level_breakdown,
    compute_total_salaries,
    create_session,
    delete_session,
    reject_session,
    submit_session,
    update_session,
)


# ============================================================
# Helpers
# ============================================================
def _require_director(u):
    if not (u.is_authenticated and (u.is_director or u.is_admin_user)):
        raise PermissionDenied(_("Page réservée au directeur des études."))


def _require_secretary(u):
    if not (u.is_authenticated and (u.is_secretary or u.is_director or u.is_admin_user)):
        raise PermissionDenied(_("Page réservée au secrétaire."))


def _require_dean(u):
    if not (u.is_authenticated and (u.is_dean or u.is_admin_user)):
        raise PermissionDenied(_("Page réservée au doyen."))


def _require_accountant(u):
    if not (u.is_authenticated and (u.is_accountant or u.is_admin_user)):
        raise PermissionDenied(_("Page réservée au comptable."))


def _require_teacher(u):
    if not (u.is_authenticated and (u.is_teacher or u.is_admin_user)):
        raise PermissionDenied(_("Page réservée aux enseignants."))


# ============================================================
# Dashboard redirect
# ============================================================
@login_required
def dashboard(request):
    u = request.user
    if u.is_superuser:
        return redirect("academics:admin_dashboard")
    if u.is_director:
        return redirect("academics:director_dashboard")
    if u.is_secretary:
        return redirect("academics:secretary_dashboard")
    if u.is_dean:
        return redirect("academics:dean_dashboard")
    if u.is_accountant:
        return redirect("academics:accountant_dashboard")
    return redirect("academics:teacher_dashboard")


# ============================================================
# TEACHER
# ============================================================
@login_required
def teacher_dashboard(request):
    _require_teacher(request.user)
    assignments = (TeachingAssignment.objects
                   .filter(teacher=request.user)
                   .select_related("subject", "level"))

    all_sessions_qs = Session.objects.filter(teacher=request.user)
    pending = all_sessions_qs.filter(status=Session.Status.SUBMITTED).count()
    total_hours = (all_sessions_qs
                   .filter(status=Session.Status.APPROVED)
                   .aggregate(t=Sum("duration_hours"))["t"] or 0)
    sessions = (all_sessions_qs
                .select_related("subject", "level")
                .order_by("-date", "-start_time")[:30])

    return render(request, "academics/teacher_dashboard.html", {
        "assignments": assignments,
        "sessions": sessions,
        "total_hours": total_hours,
        "pending": pending,
    })


@login_required
def teacher_session_create(request):
    _require_teacher(request.user)
    if request.method == "POST":
        form = SessionForm(request.POST, teacher=request.user)
        if form.is_valid():
            try:
                create_session(
                    teacher=request.user,
                    assignment=form.cleaned_data["assignment"],
                    date=form.cleaned_data["date"],
                    topic=form.cleaned_data["topic"],
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(request, _("Séance enregistrée comme brouillon."))
                return redirect("academics:teacher_dashboard")
            except Exception as e:
                form.add_error(None, str(e))
    else:
        form = SessionForm(teacher=request.user)
    return render(request, "academics/session_form.html", {"form": form, "is_edit": False})


@login_required
def teacher_session_edit(request, pk):
    _require_teacher(request.user)
    s = get_object_or_404(Session, pk=pk)
    if s.teacher_id != request.user.id:
        raise PermissionDenied(_("Cette séance ne vous appartient pas."))
    if not s.is_editable_by_teacher:
        messages.error(request, _("Cette séance ne peut plus être modifiée."))
        return redirect("academics:teacher_dashboard")

    if request.method == "POST":
        form = SessionEditForm(request.POST, instance=s)
        if form.is_valid():
            try:
                update_session(session=s, user=request.user,
                               topic=form.cleaned_data["topic"],
                               notes=form.cleaned_data.get("notes", ""))
                messages.success(request, _("Séance mise à jour."))
                return redirect("academics:teacher_dashboard")
            except (SessionLockedError, WorkflowError) as e:
                form.add_error(None, str(e))
    else:
        form = SessionEditForm(instance=s)
    return render(request, "academics/session_form.html",
                  {"form": form, "is_edit": True, "session": s})


@login_required
def teacher_session_submit(request, pk):
    _require_teacher(request.user)
    s = get_object_or_404(Session, pk=pk)
    if request.method == "POST":
        try:
            submit_session(session=s, user=request.user)
            messages.success(request, _("Séance envoyée pour validation."))
        except Exception as e:
            messages.error(request, str(e))
    return redirect("academics:teacher_dashboard")


# ============================================================
# DIRECTOR
# ============================================================
@login_required
def director_dashboard(request):
    _require_director(request.user)
    pending_sessions = (Session.objects
                        .filter(status=Session.Status.SUBMITTED)
                        .select_related("teacher", "subject", "level")
                        .order_by("submitted_at"))
    assignments = (TeachingAssignment.objects
                   .select_related("teacher", "subject", "level")
                   .order_by("teacher__display_name_fr", "weekday", "start_time"))
    recent_sessions = (Session.objects
                       .select_related("teacher", "subject", "level")
                       .order_by("-date", "-start_time")[:30])
    teacher_count = (assignments.values("teacher_id").distinct().count())

    return render(request, "academics/director_dashboard.html", {
        "pending_sessions": pending_sessions,
        "assignments": assignments,
        "recent_sessions": recent_sessions,
        "pending_count": pending_sessions.count(),
        "teacher_count": teacher_count,
    })


@login_required
def director_assignment_create(request):
    _require_director(request.user)
    if request.method == "POST":
        form = AssignmentForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.created_by = request.user
            a.save()
            messages.success(request, _("Affectation créée."))
            return redirect("academics:director_dashboard")
    else:
        form = AssignmentForm()
    return render(request, "academics/assignment_form.html", {"form": form})


@login_required
def director_session_review(request, pk):
    _require_director(request.user)
    s = get_object_or_404(Session, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "approve":
            try:
                approve_session(session=s, user=request.user)
                messages.success(request, _("Séance approuvée."))
                return redirect("academics:director_dashboard")
            except Exception as e:
                messages.error(request, str(e))

        elif action == "reject":
            form = RejectForm(request.POST)
            if form.is_valid():
                try:
                    reject_session(session=s, user=request.user,
                                   reason=form.cleaned_data["reason"])
                    messages.success(request, _("Séance rejetée."))
                    return redirect("academics:director_dashboard")
                except Exception as e:
                    messages.error(request, str(e))

        elif action == "delete":
            if not request.user.is_superuser:
                messages.error(request, _("Seul l'administrateur peut supprimer."))
            else:
                try:
                    delete_session(session=s, user=request.user)
                    messages.success(request, _("Séance supprimée définitivement."))
                    return redirect("academics:director_dashboard")
                except Exception as e:
                    messages.error(request, str(e))

    form = RejectForm()
    return render(request, "academics/session_review.html",
                  {"session": s, "form": form})


@login_required
def director_session_edit(request, pk):
    _require_director(request.user)
    s = get_object_or_404(Session, pk=pk)
    if request.method == "POST":
        form = SessionEditForm(request.POST, instance=s)
        if form.is_valid():
            update_session(session=s, user=request.user,
                           topic=form.cleaned_data["topic"],
                           notes=form.cleaned_data.get("notes", ""))
            messages.success(request, _("Documentation mise à jour."))
            return redirect("academics:director_dashboard")
    else:
        form = SessionEditForm(instance=s)
    return render(request, "academics/session_form.html",
                  {"form": form, "is_edit": True, "session": s})


# ============================================================
# SECRETARY
# ============================================================
@login_required
def secretary_dashboard(request):
    _require_secretary(request.user)
    assignments = (TeachingAssignment.objects
                   .select_related("teacher", "subject", "level", "created_by")
                   .order_by("-created_at"))
    return render(request, "academics/secretary_dashboard.html", {
        "assignments": assignments,
    })


@login_required
def secretary_assignment_create(request):
    _require_secretary(request.user)
    if request.method == "POST":
        form = AssignmentForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.created_by = request.user
            a.save()
            if request.user.is_secretary:
                from .services_notifications import notify_assignment_created_by_secretary
                try:
                    notify_assignment_created_by_secretary(a, request.user)
                except Exception:
                    pass
            messages.success(request, _("Affectation créée par le secrétaire."))
            return redirect("academics:secretary_dashboard")
    else:
        form = AssignmentForm()
    return render(request, "academics/assignment_form.html",
                  {"form": form, "back_url": "academics:secretary_dashboard"})


# ============================================================
# DEAN
# ============================================================
@login_required
def dean_dashboard(request):
    _require_dean(request.user)
    total_assignments = TeachingAssignment.objects.count()
    total_sessions = Session.objects.count()
    total_approved = Session.objects.filter(status=Session.Status.APPROVED).count()
    total_pending = Session.objects.filter(status=Session.Status.SUBMITTED).count()
    total_hours = (Session.objects
                   .filter(status=Session.Status.APPROVED)
                   .aggregate(total=Sum("duration_hours"))["total"] or 0)

    assignments_progress = []
    for a in TeachingAssignment.objects.select_related("teacher", "subject", "level"):
        assignments_progress.append({
            "assignment": a,
            "planned": a.planned_hours,
            "done": a.completed_hours,
            "remaining": a.remaining_hours,
            "percent": a.progress_percent,
        })

    recent = Session.objects.select_related("teacher", "subject").order_by("-date")[:15]

    return render(request, "academics/dean_dashboard.html", {
        "total_assignments": total_assignments,
        "total_sessions": total_sessions,
        "total_approved": total_approved,
        "total_pending": total_pending,
        "total_hours": total_hours,
        "assignments_progress": assignments_progress,
        "recent": recent,
    })


# ============================================================
# ADMIN
# ============================================================
@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        raise PermissionDenied(_("Page réservée à l'administrateur système."))
    from django.contrib.auth import get_user_model
    User = get_user_model()

    total_users = User.objects.count()
    total_assignments = TeachingAssignment.objects.count()
    total_sessions = Session.objects.count()
    total_approved = Session.objects.filter(status=Session.Status.APPROVED).count()
    total_pending = Session.objects.filter(status=Session.Status.SUBMITTED).count()
    total_rejected = Session.objects.filter(status=Session.Status.REJECTED).count()
    total_hours = (Session.objects
                   .filter(status=Session.Status.APPROVED)
                   .aggregate(total=Sum("duration_hours"))["total"] or 0)

    assignments_progress = []
    for a in TeachingAssignment.objects.select_related("teacher", "subject", "level"):
        assignments_progress.append({
            "assignment": a,
            "planned": a.planned_hours,
            "done": a.completed_hours,
            "remaining": a.remaining_hours,
            "percent": a.progress_percent,
        })

    recent = (Session.objects
              .select_related("teacher", "subject", "level")
              .order_by("-created_at")[:20])
    users_list = User.objects.all().order_by("role", "username")

    return render(request, "academics/admin_dashboard.html", {
        "total_users": total_users,
        "total_assignments": total_assignments,
        "total_sessions": total_sessions,
        "total_approved": total_approved,
        "total_pending": total_pending,
        "total_rejected": total_rejected,
        "total_hours": total_hours,
        "assignments_progress": assignments_progress,
        "recent": recent,
        "users_list": users_list,
    })


@login_required
def admin_session_delete(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied(_("Seul l'administrateur système peut supprimer."))
    s = get_object_or_404(Session, pk=pk)
    if request.method == "POST":
        s.delete()
        messages.success(request, _("Séance supprimée définitivement."))
    return redirect("academics:admin_dashboard")


# ============================================================
# ACCOUNTANT
# ============================================================
@login_required
def accountant_dashboard(request):
    _require_accountant(request.user)
    from django.contrib.auth import get_user_model
    User = get_user_model()

    df = request.GET.get("date_from") or None
    dt = request.GET.get("date_to") or None
    df_p = date.fromisoformat(df) if df else None
    dt_p = date.fromisoformat(dt) if dt else None

    f_teacher = request.GET.get("teacher") or None
    f_level = request.GET.get("level") or None
    f_subject = request.GET.get("subject") or None

    levels_summary = compute_levels_summary(date_from=df_p, date_to=dt_p)
    grand_total = compute_levels_grand_total(date_from=df_p, date_to=dt_p)
    breakdown = compute_teacher_level_breakdown(date_from=df_p, date_to=dt_p)
    salaries = compute_all_teachers_salaries(date_from=df_p, date_to=dt_p)
    total_salaries = compute_total_salaries(date_from=df_p, date_to=dt_p)

    if f_teacher:
        try:
            fid = int(f_teacher)
            breakdown = [b for b in breakdown if b["teacher"].id == fid]
            salaries = [s for s in salaries if s["teacher_id"] == fid]
        except (ValueError, TypeError):
            pass
    if f_level:
        try:
            fid = int(f_level)
            breakdown = [b for b in breakdown if b["level"].id == fid]
        except (ValueError, TypeError):
            pass
    if f_subject:
        try:
            fid = int(f_subject)
            breakdown = [b for b in breakdown if b["subject"].id == fid]
        except (ValueError, TypeError):
            pass

    from .models import Level, Subject
    teachers_list = User.objects.filter(role=User.Role.TEACHER).order_by("display_name_fr")
    levels_list = Level.objects.all().order_by("order", "name_fr")
    subjects_list = Subject.objects.all().order_by("name_fr")

    breakdown_totals = {
        "planned_hours": sum(b["planned_hours"] for b in breakdown),
        "planned_sessions": sum(b["planned_sessions"] for b in breakdown),
        "completed_hours": sum(b["completed_hours"] for b in breakdown),
        "completed_sessions": sum(b["completed_sessions"] for b in breakdown),
        "remaining_hours": sum(b["remaining_hours"] for b in breakdown),
    }
    breakdown_totals["percent"] = (
        round(100 * breakdown_totals["completed_hours"] / breakdown_totals["planned_hours"])
        if breakdown_totals["planned_hours"] else 0
    )

    return render(request, "academics/accountant_dashboard.html", {
        "teachers_hours": compute_all_teachers_hours(date_from=df_p, date_to=dt_p),
        "levels_summary": list(levels_summary.values()),
        "grand_total": grand_total,
        "breakdown": breakdown,
        "breakdown_totals": breakdown_totals,
        "salaries": salaries,
        "total_salaries": total_salaries,
        "teachers_list": teachers_list,
        "levels_list": levels_list,
        "subjects_list": subjects_list,
        "f_teacher": f_teacher or "",
        "f_level": f_level or "",
        "f_subject": f_subject or "",
        "date_from": df or "",
        "date_to": dt or "",
        "filters_active": bool(f_teacher or f_level or f_subject),
    })


@login_required
def accountant_teacher_detail(request, teacher_id):
    _require_accountant(request.user)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    t = get_object_or_404(User, pk=teacher_id, role=User.Role.TEACHER)

    df = request.GET.get("date_from") or None
    dt = request.GET.get("date_to") or None
    df_p = date.fromisoformat(df) if df else None
    dt_p = date.fromisoformat(dt) if dt else None

    qs = Session.objects.filter(teacher=t, status=Session.Status.APPROVED)
    if df_p:
        qs = qs.filter(date__gte=df_p)
    if dt_p:
        qs = qs.filter(date__lte=dt_p)
    sessions = qs.order_by("-date", "-start_time")

    hours = compute_teacher_hours(teacher=t, date_from=df_p, date_to=dt_p)

    return render(request, "academics/accountant_teacher_detail.html", {
        "teacher": t,
        "sessions": sessions,
        "hours": hours,
        "date_from": df or "",
        "date_to": dt or "",
    })


# ============================================================
# PAYSLIPS (Fiches de paie)
# ============================================================
@login_required
def accountant_payslips(request):
    """لوحة المحاسب — كشوف الرواتب.
    متاحة للمحاسب + المدير + العميد + الأدمين.
    """
    if not (request.user.is_accountant or request.user.is_director
            or request.user.is_dean or request.user.is_admin_user):
        raise PermissionDenied(_("Accès réservé au comptable, directeur, doyen ou administrateur."))

    from datetime import date as d
    from .models import Payslip
    from .services import generate_monthly_payslips

    today = d.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    if request.method == "POST" and request.POST.get("action") == "generate":
        try:
            generate_monthly_payslips(year=year, month=month)
            messages.success(request, _("Fiches générées."))
        except Exception as e:
            messages.error(request, str(e))
        return redirect(f"{request.path}?year={year}&month={month}")

    payslips = Payslip.objects.filter(year=year, month=month).select_related(
        "teacher", "paid_by",
    ).order_by("teacher__display_name_fr")

    total_paid = sum(p.total_amount for p in payslips if p.status == Payslip.Status.PAID)
    total_pending = sum(p.total_amount for p in payslips if p.status == Payslip.Status.PENDING)

    return render(request, "academics/accountant_payslips.html", {
        "payslips": payslips,
        "year": year,
        "month": month,
        "total_paid": total_paid,
        "total_pending": total_pending,
    })


@login_required
def accountant_payslip_mark_paid(request, pk):
    if not (request.user.is_accountant or request.user.is_admin_user):
        raise PermissionDenied(_("Action réservée au comptable."))
    from .models import Payslip
    from .services import mark_payslip_as_paid

    p = get_object_or_404(Payslip, pk=pk)
    if request.method == "POST":
        try:
            mark_payslip_as_paid(payslip=p, user=request.user)
            messages.success(request, _("Fiche marquée payée."))
        except Exception as e:
            messages.error(request, str(e))
    return redirect("academics:accountant_payslips")


@login_required
def accountant_payslip_mark_pending(request, pk):
    if not (request.user.is_accountant or request.user.is_admin_user):
        raise PermissionDenied(_("Action réservée au comptable."))
    from .models import Payslip
    from .services import mark_payslip_as_pending

    p = get_object_or_404(Payslip, pk=pk)
    if request.method == "POST":
        try:
            mark_payslip_as_pending(payslip=p, user=request.user)
            messages.success(request, _("Fiche remise en attente."))
        except Exception as e:
            messages.error(request, str(e))
    return redirect("academics:accountant_payslips")


# ============================================================
# DEAN FINANCES
# ============================================================
@login_required
def dean_finances(request):
    if not (request.user.is_dean or request.user.is_director or request.user.is_admin_user):
        raise PermissionDenied(_("Page réservée au doyen ou directeur."))
    from datetime import date as d
    from .models import Payslip
    from django.db.models import Sum

    today = d.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    payslips = Payslip.objects.filter(year=year, month=month).select_related("teacher")
    paid = payslips.filter(status=Payslip.Status.PAID)
    pending = payslips.filter(status=Payslip.Status.PENDING)

    stats = {
        "total_paid": paid.aggregate(t=Sum("total_amount"))["t"] or 0,
        "total_pending": pending.aggregate(t=Sum("total_amount"))["t"] or 0,
        "count_paid": paid.count(),
        "count_pending": pending.count(),
    }

    return render(request, "academics/dean_finances.html", {
        "payslips": payslips,
        "year": year,
        "month": month,
        "stats": stats,
    })


# ============================================================
# NOTIFICATIONS
# ============================================================
@login_required
def notifications_list(request):
    from .models import Notification
    notifs = Notification.objects.filter(recipient=request.user)[:50]
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return render(request, "academics/notifications.html", {
        "notifications": notifs,
    })


@login_required
def notification_open(request, pk):
    from .models import Notification
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.mark_as_read()
    if notif.url:
        return redirect(notif.url)
    return redirect("academics:notifications_list")
