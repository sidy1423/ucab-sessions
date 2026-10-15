"""
fix_all.py — إصلاح شامل للنظام في ضربة واحدة.

يقوم بـ:
1. إصلاح services.py (إعادة كتابة نظيفة)
2. إصلاح views.py (إعادة كتابة director_session_review)
3. إضافة زر الحذف في session_review.html
4. إضافة زر العودة في كل الصفحات
5. إصلاح عدد المعلمين في director_dashboard
6. إصلاح زر Réviser/Modifier الديناميكي
7. حذف ملفات .html.py المكررة

طريقة الاستخدام:
    python fix_all.py
"""

import os
import re
import sys
from pathlib import Path


# ============================================================
# محتوى الملفات الكاملة
# ============================================================

SERVICES_PY = '''"""منطق الأعمال: إنشاء/تعديل/اعتماد حصة، قفل 24 ساعة، حساب الساعات."""
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
'''


# ============================================================
# دوال التنفيذ
# ============================================================

def write_file(path, content):
    """كتابة ملف بـ UTF-8 بدون BOM."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  [+] {path}")


def fix_services():
    """إصلاح services.py بإعادة كتابته كاملًا."""
    print("\n=== 1) إصلاح services.py ===")
    write_file("academics/services.py", SERVICES_PY)


def fix_director_review_view():
    """إصلاح director_session_review في views.py."""
    print("\n=== 2) إصلاح director_session_review ===")
    path = "academics/views.py"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    pattern = r"@login_required\ndef director_session_review\(request, pk\):.*?(?=\n@login_required|\n\ndef |\Z)"

    new_func = '''@login_required
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
                from .services import delete_session
                try:
                    delete_session(session=s, user=request.user)
                    messages.success(request, _("Séance supprimée définitivement."))
                    return redirect("academics:director_dashboard")
                except Exception as e:
                    messages.error(request, str(e))

    form = RejectForm()
    return render(request, "academics/session_review.html",
                  {"session": s, "form": form})
'''

    if re.search(pattern, content, flags=re.DOTALL):
        content = re.sub(pattern, new_func, content, count=1, flags=re.DOTALL)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"  [+] {path}")
    else:
        print(f"  [!] pattern introuvable dans {path}")


def fix_director_dashboard_view():
    """إصلاح director_dashboard — إضافة teacher_count."""
    print("\n=== 3) إضافة teacher_count في director_dashboard ===")
    path = "academics/views.py"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    pattern = r"@login_required\ndef director_dashboard\(request\):.*?(?=\n@login_required|\n\ndef |\Z)"

    new_func = '''@login_required
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

    teacher_count = (assignments
                     .values("teacher_id")
                     .distinct()
                     .count())

    return render(request, "academics/director_dashboard.html", {
        "pending_sessions": pending_sessions,
        "assignments": assignments,
        "recent_sessions": recent_sessions,
        "pending_count": pending_sessions.count(),
        "teacher_count": teacher_count,
    })
'''

    if re.search(pattern, content, flags=re.DOTALL):
        content = re.sub(pattern, new_func, content, count=1, flags=re.DOTALL)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"  [+] {path}")
    else:
        print(f"  [!] pattern introuvable")


def fix_director_dashboard_template():
    """إصلاح قالب director_dashboard — استخدام teacher_count."""
    print("\n=== 4) إصلاح director_dashboard.html ===")
    path = "templates/academics/director_dashboard.html"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    # استبدال assignments|length بـ teacher_count
    content = re.sub(
        r'<h6 class="text-success">\{% trans "Enseignants" %\}</h6>\s*<h3>\{\{ assignments\|length \}\}</h3>',
        '<h6 class="text-success">{% trans "Enseignants" %}</h6>\n    <h3>{{ teacher_count }}</h3>',
        content
    )

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  [+] {path}")


def fix_session_review_template():
    """إصلاح session_review.html — إضافة زر الحذف للأدمين + زر عودة."""
    print("\n=== 5) إصلاح session_review.html ===")
    path = "templates/academics/session_review.html"

    content = '''{% extends "base.html" %}
{% load i18n %}
{% block title %}{% trans "Réviser la séance" %}{% endblock %}
{% block content %}
<h3>{% trans "Réviser la séance" %}</h3>

<div class="card mb-4">
  <div class="card-body">
    <p><strong>{% trans "Enseignant" %}:</strong> {{ session.teacher }}</p>
    <p><strong>{% trans "Matière" %}:</strong> {{ session.subject }}</p>
    <p><strong>{% trans "Niveau" %}:</strong> {{ session.level }}</p>
    <p><strong>{% trans "Date" %}:</strong> {{ session.date }} — {{ session.start_time }}</p>
    <p><strong>{% trans "Durée" %}:</strong> {{ session.duration_hours }} h</p>
    <p><strong>{% trans "Sujet" %}:</strong> {{ session.topic }}</p>
    {% if session.notes %}
      <p><strong>{% trans "Remarques" %}:</strong> {{ session.notes }}</p>
    {% endif %}
    <p><strong>{% trans "Statut" %}:</strong>
      {% if session.status == "submitted" %}<span class="badge bg-warning text-dark">{% trans "En attente" %}</span>
      {% elif session.status == "draft" %}<span class="badge bg-secondary">{% trans "Brouillon" %}</span>
      {% elif session.status == "approved" %}<span class="badge bg-success">{% trans "Approuvée" %}</span>
      {% elif session.status == "rejected" %}<span class="badge bg-danger">{% trans "Rejetée" %}</span>
      {% endif %}
    </p>
    {% if session.submitted_at %}
      <p><strong>{% trans "Envoyée" %}:</strong> {{ session.submitted_at }}</p>
    {% endif %}
  </div>
</div>

<div class="row">
  <div class="col-md-6">
    <form method="post" class="mb-3">
      {% csrf_token %}
      <input type="hidden" name="action" value="approve">
      <button class="btn btn-success w-100">✅ {% trans "Approuver" %}</button>
    </form>
  </div>
  <div class="col-md-6">
    <form method="post">
      {% csrf_token %}
      <input type="hidden" name="action" value="reject">
      {{ form.as_p }}
      <button class="btn btn-danger w-100">❌ {% trans "Rejeter" %}</button>
    </form>
  </div>
</div>

{% if user.is_superuser %}
  <hr>
  <form method="post" onsubmit="return confirm('{% trans "Confirmer la suppression définitive ?" %}');">
    {% csrf_token %}
    <input type="hidden" name="action" value="delete">
    <button class="btn btn-outline-danger w-100">🗑️ {% trans "Supprimer définitivement" %}</button>
  </form>
{% endif %}

<div class="mt-4">
  <a href="{% url 'academics:director_dashboard' %}" class="btn btn-outline-secondary">
    ← {% trans "Retour au tableau de bord" %}
  </a>
</div>
{% endblock %}
'''
    write_file(path, content)


def fix_dynamic_review_button():
    """إصلاح زر Réviser/Modifier الديناميكي في director_dashboard.html."""
    print("\n=== 6) زر Réviser/Modifier الديناميكي ===")
    path = "templates/academics/director_dashboard.html"
    with open(path, encoding="utf-8") as f:
        content = f.read()

    old = '''<a class="btn btn-sm btn-warning" href="{% url 'academics:director_session_edit' s.pk %}">
            {% trans "Modifier" %}
          </a>'''

    new = '''{% if s.status == "submitted" %}
            <a class="btn btn-sm btn-primary" href="{% url 'academics:director_session_review' s.pk %}">
              🔍 {% trans "Réviser" %}
            </a>
          {% else %}
            <a class="btn btn-sm btn-warning" href="{% url 'academics:director_session_edit' s.pk %}">
              ✏️ {% trans "Modifier" %}
            </a>
          {% endif %}'''

    if old in content:
        content = content.replace(old, new)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print(f"  [+] {path}")
    else:
        print(f"  [!] pattern introuvable")


def add_back_buttons():
    """إضافة زر العودة إلى القوالب."""
    print("\n=== 7) إضافة أزرار العودة ===")

    back_btn = '''
<div class="mt-4">
  <a href="{% url 'academics:dashboard' %}" class="btn btn-outline-secondary">
    ← {% trans "Retour au tableau de bord" %}
  </a>
</div>
'''

    templates = [
        "templates/academics/session_form.html",
        "templates/academics/assignment_form.html",
        "templates/academics/notifications.html",
    ]

    for tpl in templates:
        p = Path(tpl)
        if not p.exists():
            print(f"  [!] absent: {tpl}")
            continue
        with open(p, encoding="utf-8") as f:
            content = f.read()
        if "Retour au tableau de bord" in content:
            print(f"  [=] {tpl} (déjà)")
            continue
        if "{% endblock %}" in content:
            content = content.replace("{% endblock %}", back_btn + "\n{% endblock %}", 1)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"  [+] {tpl}")


def cleanup_html_py_files():
    """حذف ملفات .html.py المكررة."""
    print("\n=== 8) تنظيف الملفات المكررة ===")
    removed = 0
    for pattern in ["**/*.html.py", "**/*.py.py"]:
        for f in Path(".").glob(pattern):
            if ".venv" in str(f):
                continue
            f.unlink()
            print(f"  [-] {f}")
            removed += 1
    print(f"  Total supprimé: {removed}")


# ============================================================
# Main
# ============================================================

def main():
    # تأكد من أننا في مجلد المشروع
    if not Path("manage.py").exists():
        print("ERREUR: manage.py introuvable. Lancez depuis le dossier du projet.")
        sys.exit(1)

    print("=" * 60)
    print("  FIX ALL — Correction complète du système")
    print("=" * 60)

    fix_services()
    fix_director_review_view()
    fix_director_dashboard_view()
    fix_director_dashboard_template()
    fix_session_review_template()
    fix_dynamic_review_button()
    add_back_buttons()
    cleanup_html_py_files()

    print("\n" + "=" * 60)
    print("  ✅ Terminé!")
    print("=" * 60)
    print("\nProchaines étapes:")
    print("  1. python manage.py check")
    print("  2. python manage.py runserver")


if __name__ == "__main__":
    main()