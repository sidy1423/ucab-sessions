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
    compute_levels_grand_total,
    compute_levels_summary,
    compute_levels_totals,
    compute_teacher_hours,
    compute_all_teachers_salaries,
    compute_teacher_level_breakdown,
    compute_total_salaries,
    create_session,
    delete_session,
    reject_session,
    submit_session,
    update_session,
)


# ---------- التحقق من الصلاحيات ----------
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


# ---------- لوحة القيادة (توجيه) ----------
@login_required
def dashboard(request):
    u = request.user
    if u.is_admin_user or u.is_director:
        return redirect("academics:director_dashboard")
    if u.is_secretary:
        return redirect("academics:secretary_dashboard")
    if u.is_dean:
        return redirect("academics:dean_dashboard")
    if u.is_accountant:
        return redirect("academics:accountant_dashboard")
    return redirect("academics:teacher_dashboard")


# ================= المعلم =================
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


# ============================================================
# PAYSLIPS — Fiches de paie (une seule version par fonction)
# ============================================================
@login_required
def accountant_payslips(request):
    """لوحة المحاسب — كشوف الرواتب.
    متاحة للمحاسب + المدير + العميد + الأدمين.
    """
    if not (request.user.is_accountant or request.user.is_director
            or request.user.is_dean or request.user.is_admin_user):
        raise PermissionDenied(_("Accès réservé au comptable, directeur, doyen ou administrateur."))

    from datetime import date
    from .models import Payslip
    from .services import generate_monthly_payslips

    today = date.today()
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


@login_required
def dean_finances(request):
    if not (request.user.is_dean or request.user.is_director or request.user.is_admin_user):
        raise PermissionDenied(_("Page réservée au doyen ou directeur."))
    from datetime import date
    from .models import Payslip
    from django.db.models import Sum

    today = date.today()
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

