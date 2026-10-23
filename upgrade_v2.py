"""
upgrade_v2.py — المالية + صلاحيات السكرتير
=========================================
- إضافة hourly_rate إلى Level
- إضافة حساب الأجر للمحاسب
- إشعار المدير عند تعديل السكرتير
- لوحة المحاسب محسّنة مع الأجر
"""

from pathlib import Path


# ============================================================
# 1) تحديث Level model — إضافة hourly_rate
# ============================================================
def update_level_model():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    old = '''class Level(models.Model):
    """Niveau / المستوى الدراسي."""
    name_fr = models.CharField(_("Nom (français)"), max_length=100, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=100, unique=True)
    order   = models.PositiveIntegerField(_("Ordre"), default=0)

    class Meta:
        ordering = ["order", "name_fr"]
        verbose_name = _("Niveau")
        verbose_name_plural = _("Niveaux")

    def __str__(self):
        return self.name_fr'''

    new = '''class Level(models.Model):
    """Niveau / المستوى الدراسي مع سعر الساعة."""
    name_fr = models.CharField(_("Nom (français)"), max_length=100, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=100, unique=True)
    order   = models.PositiveIntegerField(_("Ordre"), default=0)
    hourly_rate = models.DecimalField(
        _("Tarif horaire (FCFA)"),
        max_digits=10, decimal_places=2, default=5000,
        help_text=_("Tarif par heure pour ce niveau (FCFA)"),
    )

    class Meta:
        ordering = ["order", "name_fr"]
        verbose_name = _("Niveau")
        verbose_name_plural = _("Niveaux")

    def __str__(self):
        return self.name_fr'''

    if old in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print("  [+] Level.hourly_rate ajouté")
    else:
        print("  [!] Level — pattern introuvable")


# ============================================================
# 2) إضافة حساب الأجر في services.py
# ============================================================
def add_salary_service():
    path = Path("academics/services.py")
    content = path.read_text(encoding="utf-8")

    new_function = '''


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
'''

    # أضف الدوال في نهاية الملف
    if "compute_teacher_salary" not in content:
        content = content.rstrip() + new_function + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] compute_teacher_salary ajouté")
    else:
        print("  [=] compute_teacher_salary existe déjà")


# ============================================================
# 3) تحديث accountant_dashboard view — إضافة الرواتب
# ============================================================
def update_accountant_view():
    path = Path("academics/views.py")
    content = path.read_text(encoding="utf-8")

    # استيراد الدوال الجديدة
    if "compute_all_teachers_salaries" not in content.split("def accountant_dashboard")[0]:
        content = content.replace(
            "    compute_teacher_level_breakdown,",
            "    compute_all_teachers_salaries,\n    compute_teacher_level_breakdown,\n    compute_total_salaries,"
        )

    # استبدل accountant_dashboard
    import re
    pattern = r"@login_required\ndef accountant_dashboard\(request\):.*?(?=\n@login_required|\n\ndef |\Z)"

    new_func = '''@login_required
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
            f_teacher_id = int(f_teacher)
            breakdown = [b for b in breakdown if b["teacher"].id == f_teacher_id]
            salaries = [s for s in salaries if s["teacher_id"] == f_teacher_id]
        except (ValueError, TypeError):
            pass
    if f_level:
        try:
            f_level_id = int(f_level)
            breakdown = [b for b in breakdown if b["level"].id == f_level_id]
        except (ValueError, TypeError):
            pass
    if f_subject:
        try:
            f_subject_id = int(f_subject)
            breakdown = [b for b in breakdown if b["subject"].id == f_subject_id]
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

'''

    content = re.sub(pattern, new_func, content, count=1, flags=re.DOTALL)

    path.write_text(content, encoding="utf-8")
    print("  [+] accountant_dashboard mis à jour (salaires)")


# ============================================================
# 4) تحديث admin.py — عرض hourly_rate
# ============================================================
def update_admin():
    path = Path("academics/admin.py")
    content = path.read_text(encoding="utf-8")

    if "hourly_rate" not in content:
        content = content.replace(
            "admin.site.register(Level)",
            '''@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name_fr", "name_ar", "order", "hourly_rate")
    list_editable = ("hourly_rate",)'''
        )
        path.write_text(content, encoding="utf-8")
        print("  [+] LevelAdmin avec hourly_rate")
    else:
        print("  [=] hourly_rate déjà dans admin")


# ============================================================
# 5) إشعار المدير عند تعديل السكرتير
# ============================================================
def add_secretary_notification():
    path = Path("academics/services_notifications.py")
    content = path.read_text(encoding="utf-8")

    new_func = '''


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
'''

    if "notify_assignment_created_by_secretary" not in content:
        content = content.rstrip() + new_func + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] notify_assignment_created_by_secretary ajoutée")
    else:
        print("  [=] déjà présent")


# ============================================================
# 6) تحديث Notification.Type — إضافة ASSIGNMENT_CREATED
# ============================================================
def update_notification_type():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    old = '''        SESSION_SUBMITTED = "session_submitted", _("Séance envoyée")
        SESSION_APPROVED  = "session_approved",  _("Séance approuvée")
        SESSION_REJECTED  = "session_rejected",  _("Séance rejetée")
        SESSION_DELETED   = "session_deleted",   _("Séance supprimée")'''

    new = '''        SESSION_SUBMITTED = "session_submitted", _("Séance envoyée")
        SESSION_APPROVED  = "session_approved",  _("Séance approuvée")
        SESSION_REJECTED  = "session_rejected",  _("Séance rejetée")
        SESSION_DELETED   = "session_deleted",   _("Séance supprimée")
        ASSIGNMENT_CREATED = "assignment_created", _("Affectation créée")'''

    if old in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print("  [+] Notification.Type.ASSIGNMENT_CREATED ajouté")
    else:
        print("  [=] déjà présent ou pattern différent")


# ============================================================
# 7) تحديث secretary_assignment_create — إرسال إشعار
# ============================================================
def update_secretary_view():
    path = Path("academics/views.py")
    content = path.read_text(encoding="utf-8")

    old = '''@login_required
def secretary_assignment_create(request):
    _require_secretary(request.user)
    if request.method == "POST":
        form = AssignmentForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.created_by = request.user
            a.save()
            messages.success(request, _("Affectation créée par le secrétaire."))
            return redirect("academics:secretary_dashboard")
    else:
        form = AssignmentForm()
    return render(request, "academics/assignment_form.html",
                  {"form": form, "back_url": "academics:secretary_dashboard"})'''

    new = '''@login_required
def secretary_assignment_create(request):
    _require_secretary(request.user)
    if request.method == "POST":
        form = AssignmentForm(request.POST)
        if form.is_valid():
            a = form.save(commit=False)
            a.created_by = request.user
            a.save()
            # إشعار المدير إذا كان السكرتير هو من أنشأ
            if request.user.is_secretary:
                from .services_notifications import notify_assignment_created_by_secretary
                notify_assignment_created_by_secretary(a, request.user)
            messages.success(request, _("Affectation créée par le secrétaire."))
            return redirect("academics:secretary_dashboard")
    else:
        form = AssignmentForm()
    return render(request, "academics/assignment_form.html",
                  {"form": form, "back_url": "academics:secretary_dashboard"})'''

    if old in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print("  [+] secretary_assignment_create — notifications ajoutées")
    else:
        print("  [!] pattern introuvable pour secretary_assignment_create")


# ============================================================
# Main
# ============================================================
def main():
    if not Path("manage.py").exists():
        print("ERREUR: manage.py introuvable")
        return

    print("=" * 60)
    print("  UPGRADE V2 — Finances + Secrétaire")
    print("=" * 60)

    print("\n=== 1) Modèles ===")
    update_level_model()
    update_notification_type()

    print("\n=== 2) Services ===")
    add_salary_service()
    add_secretary_notification()

    print("\n=== 3) Views ===")
    update_accountant_view()
    update_secretary_view()

    print("\n=== 4) Admin ===")
    update_admin()

    print("\n" + "=" * 60)
    print("  ✅ Terminé !")
    print("=" * 60)
    print("\nProchaines étapes :")
    print("  1. python manage.py makemigrations")
    print("  2. python manage.py migrate")
    print("  3. python manage.py check")


if __name__ == "__main__":
    main()