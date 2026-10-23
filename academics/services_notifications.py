"""خدمات الإشعارات — إنشاء إشعارات تلقائية عند الأحداث."""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import Notification, Session


def _create_notification(*, recipient, notif_type, message, url=""):
    """إنشاء إشعار واحد."""
    if recipient is None:
        return None
    return Notification.objects.create(
        recipient=recipient,
        type=notif_type,
        message=message,
        url=url,
    )


def notify_session_submitted(session):
    """إشعار المدير عندما يرسل معلم حصة."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # أرسل لكل مديري الدراسات
    directors = User.objects.filter(role=User.Role.DIRECTOR)
    url = reverse("academics:director_session_review", args=[session.pk])
    for d in directors:
        _create_notification(
            recipient=d,
            notif_type=Notification.Type.SESSION_SUBMITTED,
            message=_(
                "%(teacher)s a envoyé une séance (%(subject)s — %(date)s) pour validation."
            ) % {
                "teacher": str(session.teacher),
                "subject": str(session.subject),
                "date": session.date.strftime("%Y-%m-%d"),
            },
            url=url,
        )


def notify_session_approved(session):
    """إشعار المعلم عند اعتماد حصته."""
    _create_notification(
        recipient=session.teacher,
        notif_type=Notification.Type.SESSION_APPROVED,
        message=_(
            "Votre séance (%(subject)s — %(date)s) a été approuvée par %(reviewer)s."
        ) % {
            "subject": str(session.subject),
            "date": session.date.strftime("%Y-%m-%d"),
            "reviewer": str(session.reviewed_by) if session.reviewed_by else "—",
        },
        url=reverse("academics:teacher_dashboard"),
    )


def notify_session_rejected(session, reason):
    """إشعار المعلم عند رفض حصته."""
    _create_notification(
        recipient=session.teacher,
        notif_type=Notification.Type.SESSION_REJECTED,
        message=_(
            "Votre séance (%(subject)s — %(date)s) a été rejetée. Motif: %(reason)s"
        ) % {
            "subject": str(session.subject),
            "date": session.date.strftime("%Y-%m-%d"),
            "reason": reason,
        },
        url=reverse("academics:teacher_dashboard"),
    )


def notify_session_deleted(session, deleted_by):
    """إشعار المعلم عند حذف حصته."""
    _create_notification(
        recipient=session.teacher,
        notif_type=Notification.Type.SESSION_DELETED,
        message=_(
            "Votre séance (%(subject)s — %(date)s) a été supprimée par %(admin)s."
        ) % {
            "subject": str(session.subject),
            "date": session.date.strftime("%Y-%m-%d"),
            "admin": str(deleted_by),
        },
        url=reverse("academics:teacher_dashboard"),
    )

def notify_late_submission(session):
    """إشعار المدير عند إرسال معلم حصة متأخرة (بعد 24h)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    directors = User.objects.filter(role=User.Role.DIRECTOR)
    url = reverse("academics:director_session_review", args=[session.pk])
    for d in directors:
        _create_notification(
            recipient=d,
            notif_type=Notification.Type.SESSION_SUBMITTED,
            message=_(
                "⚠️ [Envoi tardif] %(teacher)s a envoyé une séance ancienne "
                "(%(subject)s — %(date)s). Vérifiez et décidez."
            ) % {
                "teacher": str(session.teacher),
                "subject": str(session.subject),
                "date": session.date.strftime("%Y-%m-%d"),
            },
            url=url,
        )


def notify_assignment_created_by_secretary(assignment, secretary):
    """إشعار المدير عند إنشاء السكرتير إسنادًا."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    User = get_user_model()

    directors = User.objects.filter(role=User.Role.DIRECTOR)
    message = (
        f"Le secrétaire {secretary.display_name_fr or secretary.username} "
        f"a créé une affectation : {assignment.subject.name_fr} "
        f"({assignment.level.name_fr}) pour {assignment.teacher.display_name_fr}"
    )
    for d in directors:
        _create_notification(
            recipient=d,
            notif_type=Notification.Type.ASSIGNMENT_CREATED,
            message=message,
            url=reverse("academics:director_dashboard"),
        )


def notify_payslip_paid(payslip):
    """إشعار المدير والعميد عند تأكيد دفع كشف راتب."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    User = get_user_model()

    recipients = User.objects.filter(role__in=[User.Role.DIRECTOR, User.Role.DEAN])
    message = (
        f"Fiche de paie payée : {payslip.teacher.display_name_fr} — "
        f"{payslip.period_label} — {payslip.total_amount} FCFA"
    )
    for r in recipients:
        _create_notification(
            recipient=r,
            notif_type=Notification.Type.PAYSLIP_PAID,
            message=message,
            url=reverse("academics:dean_dashboard"),
        )

