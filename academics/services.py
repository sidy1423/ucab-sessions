"""منطق الأعمال: إنشاء/تعديل/اعتماد حصة، قفل 24 ساعة، حساب الساعات."""
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Session, TeachingAssignment
from .services_notifications import (
    notify_late_submission,
    notify_session_approved,
    notify_session_deleted,
    notify_session_rejected,
    notify_session_submitted,
)


class SessionLockedError(PermissionDenied):
    pass


class DuplicateSessionError(ValidationError):
    pass


class WorkflowError(ValidationError):
    pass


def create_session(*, teacher, assignment, date, topic, notes=""):
    """إنشاء حصة جديدة (draft)."""
    if assignment.teacher_id != teacher.id:
        raise PermissionDenied(_("Cette affectation ne vous appartient pas."))
    if date.weekday() > 5:
        raise ValidationError(_("Les jours d'étude vont du lundi au samedi."))
    if date.weekday() != assignment.weekday:
        raise ValidationError(_("La date ne correspond pas au jour de l'affectation."))
    if Session.objects.filter(assignment=assignment, date=date).exists():
        raise DuplicateSessionError(_("Cette séance est déjà documentée à cette date."))

    s = Session(
        assignment=assignment,
        date=date,
        topic=topic,
        notes=notes or "",
        status=Session.Status.DRAFT,
        last_edited_by=teacher,
    )
    s.teacher_id = assignment.teacher_id
    s.subject_id = assignment.subject_id
    s.level_id = assignment.level_id
    s.weekday = assignment.weekday
    s.start_time = assignment.start_time
    s.duration_hours = assignment.duration_hours

    s.full_clean(exclude=["assignment"])
    s.save()
    return s


def update_session(*, session, user, topic=None, notes=None):
    """تعديل حصة مع احترام الصلاحيات وقفل 24 ساعة."""
    if user.is_admin_user or user.is_director:
        pass
    elif user.is_teacher:
        if session.teacher_id != user.id:
            raise PermissionDenied(_("Cette séance ne vous appartient pas."))
        if session.is_locked():
            raise SessionLockedError(_("Délai de 24h dépassé : modification impossible."))
        if session.status not in (Session.Status.DRAFT, Session.Status.REJECTED):
            raise WorkflowError(_("Cette séance ne peut plus être modifiée dans son état actuel."))
    elif user.is_secretary:
        if session.status not in (Session.Status.DRAFT, Session.Status.REJECTED):
            raise WorkflowError(_("Le secrétaire ne peut modifier que les brouillons ou rejets."))
    else:
        raise PermissionDenied(_("Vous n'avez pas la permission de modifier."))

    if topic is not None:
        session.topic = topic
    if notes is not None:
        session.notes = notes
    session.last_edited_by = user
    session.full_clean(exclude=["assignment", "teacher", "subject", "level",
                                "weekday", "start_time", "duration_hours"])
    session.save()
    return session


def submit_session(*, session, user):
    """المعلم يرسل الحصة للمراجعة (draft/rejected -> submitted)."""
    if session.teacher_id != user.id:
        raise PermissionDenied(_("Cette séance ne vous appartient pas."))

    if session.status not in (Session.Status.DRAFT, Session.Status.REJECTED):
        raise WorkflowError(_("Seuls les brouillons et rejets peuvent être envoyés."))

    if session.is_locked():
        if session.session_end < timezone.now() - timedelta(days=30):
            raise SessionLockedError(
                _("Séance trop ancienne (plus de 30 jours) : contactez le directeur.")
            )
        session.status = Session.Status.SUBMITTED
        session.submitted_at = timezone.now()
        session.last_edited_by = user
        if session.notes:
            session.notes = session.notes + " [Envoi tardif]"
        else:
            session.notes = "[Envoi tardif — après le délai de 24h]"
        session.save()
        notify_late_submission(session)
        return session

    session.status = Session.Status.SUBMITTED
    session.submitted_at = timezone.now()
    session.last_edited_by = user
    session.save()
    notify_session_submitted(session)
    return session


def approve_session(*, session, user):
    """المدير يعتمد الحصة (submitted أو draft)."""
    if not (user.is_director or user.is_admin_user):
        raise PermissionDenied(_("Seul le directeur des études peut approuver."))
    if session.status not in (Session.Status.SUBMITTED, Session.Status.DRAFT):
        raise WorkflowError(_("Seules les séances en attente ou brouillon peuvent être approuvées."))

    session.status = Session.Status.APPROVED
    session.reviewed_at = timezone.now()
    session.reviewed_by = user
    session.rejection_reason = ""
    session.save()
    notify_session_approved(session)
    return session


def reject_session(*, session, user, reason):
    """المدير يرفض الحصة."""
    if not (user.is_director or user.is_admin_user):
        raise PermissionDenied(_("Seul le directeur des études peut rejeter."))
    if session.status != Session.Status.SUBMITTED:
        raise WorkflowError(_("Seules les séances en attente peuvent être rejetées."))
    if not reason.strip():
        raise ValidationError(_("Le motif de rejet est obligatoire."))

    session.status = Session.Status.REJECTED
    session.reviewed_at = timezone.now()
    session.reviewed_by = user
    session.rejection_reason = reason
    session.save()
    notify_session_rejected(session, reason)
    return session


def delete_session(*, session, user):
    """حذف حصة — فقط للأدمين."""
    if not user.is_superuser:
        raise PermissionDenied(_("Seul l'administrateur système peut supprimer des séances."))
    notify_session_deleted(session, user)
    session.delete()


def lock_expired_sessions():
    now = timezone.now()
    count = 0
    for s in Session.objects.filter(locked_at__isnull=True).iterator():
        if s.is_locked():
            s.locked_at = now
            s.save(update_fields=["locked_at"])
            count += 1
    return count


@dataclass
class TeacherHours:
    teacher_id: int
    teacher_name: str
    total_hours: int
    by_level: dict


def compute_teacher_hours(*, teacher, date_from=None, date_to=None):
    qs = Session.objects.filter(teacher=teacher, status=Session.Status.APPROVED)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    rows = (qs.values("level_id", "level__name_fr")
              .annotate(hours=Sum("duration_hours"))
              .order_by("level__name_fr"))

    by_level, total = {}, 0
    for r in rows:
        by_level[r["level_id"]] = {"name": r["level__name_fr"], "hours": r["hours"] or 0}
        total += r["hours"] or 0
    return TeacherHours(teacher.id, str(teacher), total, by_level)


def compute_all_teachers_hours(*, date_from=None, date_to=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return [compute_teacher_hours(teacher=t, date_from=date_from, date_to=date_to)
            for t in User.objects.filter(role=User.Role.TEACHER)]


def compute_levels_totals(*, date_from=None, date_to=None):
    qs = Session.objects.filter(status=Session.Status.APPROVED)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    rows = (qs.values("level_id", "level__name_fr")
              .annotate(hours=Sum("duration_hours"), sessions=Count("id"))
              .order_by("level__name_fr"))
    return {r["level_id"]: {"name": r["level__name_fr"],
                            "hours": r["hours"] or 0,
                            "sessions": r["sessions"]} for r in rows}


def compute_levels_summary(*, date_from=None, date_to=None):
    """ملخص كامل لكل مستوى."""
    from .models import Level

    result = {}
    for level in Level.objects.all().order_by("order", "name_fr"):
        assignments = TeachingAssignment.objects.filter(level=level)
        planned_sessions = sum(a.planned_sessions for a in assignments)
        planned_hours = sum(a.planned_hours for a in assignments)

        qs = Session.objects.filter(level=level, status=Session.Status.APPROVED)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        agg = qs.aggregate(hours=Sum("duration_hours"), sessions=Count("id"))
        completed_hours = agg["hours"] or 0
        completed_sessions = agg["sessions"] or 0

        result[level.id] = {
            "name": level.name_fr,
            "planned_sessions": planned_sessions,
            "planned_hours": planned_hours,
            "completed_sessions": completed_sessions,
            "completed_hours": completed_hours,
            "remaining_hours": max(0, planned_hours - completed_hours),
            "percent": round(100 * completed_hours / planned_hours) if planned_hours else 0,
        }
    return result


def compute_teacher_level_breakdown(*, date_from=None, date_to=None):
    """تفصيل: كل معلم × مادة × مستوى."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    result = []
    for teacher in User.objects.filter(role=User.Role.TEACHER).order_by("display_name_fr"):
        for assignment in teacher.assignments.select_related("level", "subject").all():
            qs = Session.objects.filter(
                teacher=teacher,
                level=assignment.level,
                subject=assignment.subject,
                status=Session.Status.APPROVED,
            )
            if date_from:
                qs = qs.filter(date__gte=date_from)
            if date_to:
                qs = qs.filter(date__lte=date_to)

            agg = qs.aggregate(hours=Sum("duration_hours"), sessions=Count("id"))
            completed_hours = agg["hours"] or 0
            completed_sessions = agg["sessions"] or 0

            if completed_sessions > 0 or assignment.planned_sessions > 0:
                result.append({
                    "teacher": teacher,
                    "level": assignment.level,
                    "subject": assignment.subject,
                    "planned_sessions": assignment.planned_sessions,
                    "planned_hours": assignment.planned_hours,
                    "completed_sessions": completed_sessions,
                    "completed_hours": completed_hours,
                    "remaining_hours": max(0, assignment.planned_hours - completed_hours),
                })
    return result


def compute_levels_grand_total(*, date_from=None, date_to=None):
    """الإجماليات الكبرى."""
    total_planned_hours = 0
    total_planned_sessions = 0
    for a in TeachingAssignment.objects.all():
        total_planned_hours += a.planned_hours
        total_planned_sessions += a.planned_sessions

    qs = Session.objects.filter(status=Session.Status.APPROVED)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    agg = qs.aggregate(hours=Sum("duration_hours"), sessions=Count("id"))
    completed_hours = agg["hours"] or 0
    completed_sessions = agg["sessions"] or 0

    return {
        "planned_hours": total_planned_hours,
        "planned_sessions": total_planned_sessions,
        "completed_hours": completed_hours,
        "completed_sessions": completed_sessions,
        "remaining_hours": max(0, total_planned_hours - completed_hours),
        "percent": round(100 * completed_hours / total_planned_hours) if total_planned_hours else 0,
    }


def compute_teacher_salary(*, teacher, date_from=None, date_to=None):
    """
    يحسب أجر المعلم بناءً على ساعاته المعتمدة × سعر المستوى.
    يعيد:
        {
            "teacher_name": str,
            "total_hours": Decimal,
            "total_amount": Decimal,
            "details": [
                {"level": str, "hours": Decimal, "rate": Decimal, "amount": Decimal},
                ...
            ]
        }
    """
    from decimal import Decimal

    qs = Session.objects.filter(
        teacher=teacher,
        status=Session.Status.APPROVED,
    )
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    # تجميع حسب المستوى
    by_level = {}
    for session in qs.select_related("level"):
        level_id = session.level_id
        if level_id not in by_level:
            by_level[level_id] = {
                "level": session.level.name_fr,
                "hours": Decimal(0),
                "rate": Decimal(session.level.hourly_rate),
                "amount": Decimal(0),
            }
        by_level[level_id]["hours"] += Decimal(session.duration_hours)

    # احسب المبلغ لكل مستوى
    total_hours = Decimal(0)
    total_amount = Decimal(0)
    for info in by_level.values():
        info["amount"] = info["hours"] * info["rate"]
        total_hours += info["hours"]
        total_amount += info["amount"]

    return {
        "teacher_name": str(teacher),
        "teacher_id": teacher.id,
        "total_hours": total_hours,
        "total_amount": total_amount,
        "details": list(by_level.values()),
    }


def compute_all_teachers_salaries(*, date_from=None, date_to=None):
    """يحسب أجر كل المعلمين."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return [
        compute_teacher_salary(teacher=t, date_from=date_from, date_to=date_to)
        for t in User.objects.filter(role=User.Role.TEACHER)
    ]


def compute_total_salaries(*, date_from=None, date_to=None):
    """إجمالي رواتب كل المعلمين."""
    from decimal import Decimal
    salaries = compute_all_teachers_salaries(date_from=date_from, date_to=date_to)
    total = Decimal(0)
    for s in salaries:
        total += s["total_amount"]
    return total


# ============================================================
# PAYSLIPS — Fiches de paie mensuelles
# ============================================================
def generate_payslip(*, teacher, year, month):
    """
    يولّد كشف راتب لمعلم/شهر بناءً على الحصص المعتمدة.
    - إذا وُجد كشف سابق (pending): يُحدّث بالأرقام الجديدة.
    - إذا كان مدفوعًا: يُرفض (لا يُعدّل).
    """
    from calendar import monthrange
    from datetime import date
    from decimal import Decimal
    from django.utils import timezone
    from .models import Payslip

    # نطاق الشهر
    _, last_day = monthrange(year, month)
    date_from = date(year, month, 1)
    date_to = date(year, month, last_day)

    # احسب الساعات والمبلغ
    salary = compute_teacher_salary(
        teacher=teacher, date_from=date_from, date_to=date_to,
    )

    payslip, created = Payslip.objects.get_or_create(
        teacher=teacher, year=year, month=month,
        defaults={"total_hours": 0, "total_amount": 0},
    )

    if payslip.status == Payslip.Status.PAID:
        raise ValueError(
            f"Fiche de paie déjà payée pour {teacher} — {month:02d}/{year}"
        )

    payslip.total_hours = salary["total_hours"]
    payslip.total_amount = salary["total_amount"]
    payslip.save()

    return payslip, created


def generate_monthly_payslips(*, year, month):
    """يولّد كشوف كل المعلمين لشهر معين."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    results = []
    for teacher in User.objects.filter(role=User.Role.TEACHER):
        try:
            payslip, created = generate_payslip(
                teacher=teacher, year=year, month=month,
            )
            results.append((payslip, created))
        except ValueError as e:
            # تجاوز المعلمين المدفوعين مسبقًا
            results.append((str(e), False))

    return results


def mark_payslip_as_paid(*, payslip, user):
    """تأكيد دفع كشف راتب."""
    from django.utils import timezone
    from .models import Payslip

    if not (user.is_accountant or user.is_admin_user):
        raise PermissionDenied(_("Seul le comptable peut confirmer le paiement."))

    if payslip.status == Payslip.Status.PAID:
        return payslip  # مدفوع مسبقًا

    payslip.status = Payslip.Status.PAID
    payslip.paid_at = timezone.now()
    payslip.paid_by = user
    payslip.save()

    # إشعار للمدير والعميد
    try:
        from .services_notifications import notify_payslip_paid
        notify_payslip_paid(payslip)
    except Exception:
        pass

    return payslip


def mark_payslip_as_pending(*, payslip, user):
    """إرجاع كشف راتب إلى حالة الانتظار (تصحيح خطأ)."""
    from .models import Payslip

    if not (user.is_admin_user or user.is_accountant):
        raise PermissionDenied(_("Action réservée au comptable ou administrateur."))

    payslip.status = Payslip.Status.PENDING
    payslip.paid_at = None
    payslip.paid_by = None
    payslip.save()
    return payslip

