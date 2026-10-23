"""
upgrade_weekly.py — الجدول الأسبوعي المتغير
==========================================
- نموذج WeeklySchedule
- السكرتير يعدّل أسبوعًا معينًا
- المدير يُشعَر
- لوحة السكرتير محسّنة
"""

from pathlib import Path


# ============================================================
# 1) نموذج WeeklySchedule
# ============================================================
def add_weekly_model():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    model = '''


class WeeklySchedule(models.Model):
    """
    جدول أسبوعي مخصص لتعديل أوقات الحصص.
    - إذا وُجد سجل لهذا الأسبوع: يستخدم بدلًا من TeachingAssignment.
    - السكرتير أو المدير ينشئه.
    - المدير يُشعَر.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        CONFIRMED = "confirmed", _("Confirmé")

    assignment = models.ForeignKey(
        TeachingAssignment, on_delete=models.CASCADE,
        related_name="weekly_overrides",
        verbose_name=_("Affectation d'origine"),
    )
    week_start = models.DateField(
        _("Début de la semaine (lundi)"),
        help_text=_("Date du lundi de la semaine concernée"),
    )

    # التعديلات (إذا None → يستخدم قيمة الأصل)
    new_weekday = models.PositiveSmallIntegerField(
        _("Nouveau jour"), null=True, blank=True,
    )
    new_start_time = models.TimeField(
        _("Nouvelle heure"), null=True, blank=True,
    )
    new_duration = models.PositiveSmallIntegerField(
        _("Nouvelle durée (h)"), null=True, blank=True,
    )
    new_teacher = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="weekly_teacher_overrides",
        verbose_name=_("Nouvel enseignant"),
    )

    reason = models.TextField(_("Motif"), blank=True)
    status = models.CharField(
        _("Statut"), max_length=20,
        choices=Status.choices, default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="weekly_created",
        verbose_name=_("Créé par"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start"]
        verbose_name = _("Horaire hebdomadaire")
        verbose_name_plural = _("Horaires hebdomadaires")
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "week_start"],
                name="uniq_weekly_override",
            )
        ]
        indexes = [
            models.Index(fields=["week_start"]),
        ]

    def __str__(self):
        return f"{self.assignment} — semaine du {self.week_start}"

    # ---- القيم الفعلية ----
    @property
    def effective_weekday(self):
        return self.new_weekday if self.new_weekday is not None else self.assignment.weekday

    @property
    def effective_start_time(self):
        return self.new_start_time or self.assignment.start_time

    @property
    def effective_duration(self):
        return self.new_duration if self.new_duration else self.assignment.duration_hours

    @property
    def effective_teacher(self):
        return self.new_teacher or self.assignment.teacher
'''

    if "class WeeklySchedule" not in content:
        content = content.rstrip() + model + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] WeeklySchedule ajouté")
    else:
        print("  [=] WeeklySchedule existe déjà")


# ============================================================
# 2) إشعار المدير عند تعديل السكرتير
# ============================================================
def add_weekly_notification():
    path = Path("academics/services_notifications.py")
    content = path.read_text(encoding="utf-8")

    func = '''


def notify_weekly_schedule_created(weekly, user):
    """إشعار المدير عند تعديل السكرتير جدولاً أسبوعيًا."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    User = get_user_model()

    directors = User.objects.filter(role=User.Role.DIRECTOR)
    message = (
        f"{user.display_name_fr} a modifié l'horaire de "
        f"{weekly.assignment.subject.name_fr} pour la semaine du {weekly.week_start}"
    )
    for d in directors:
        _create_notification(
            recipient=d,
            notif_type=Notification.Type.WEEKLY_SCHEDULE_CREATED,
            message=message,
            url=reverse("academics:director_weekly_list"),
        )
'''

    if "notify_weekly_schedule_created" not in content:
        content = content.rstrip() + func + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] notify_weekly_schedule_created ajoutée")
    else:
        print("  [=] existe déjà")


# ============================================================
# 3) تحديث Notification.Type
# ============================================================
def update_notif_type():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    old = '''        PAYSLIP_PAID = "payslip_paid", _("Fiche de paie payée")'''

    new = '''        PAYSLIP_PAID = "payslip_paid", _("Fiche de paie payée")
        WEEKLY_SCHEDULE_CREATED = "weekly_schedule_created", _("Horaire hebdomadaire modifié")'''

    if old in content and "WEEKLY_SCHEDULE_CREATED" not in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print("  [+] Notification.Type.WEEKLY_SCHEDULE_CREATED ajouté")
    else:
        print("  [=] déjà présent")


# ============================================================
# 4) View: secretary_weekly_create
# ============================================================
def add_weekly_views():
    path = Path("academics/views.py")
    content = path.read_text(encoding="utf-8")

    views = '''


# ============================================================
# WEEKLY SCHEDULE (Horaire hebdomadaire)
# ============================================================
@login_required
def secretary_weekly_list(request):
    """قائمة التعديلات الأسبوعية للسكرتير."""
    _require_secretary(request.user)
    from .models import WeeklySchedule
    weeklies = (WeeklySchedule.objects
                .select_related("assignment__teacher", "assignment__subject", "created_by")
                .order_by("-week_start"))
    return render(request, "academics/secretary_weekly_list.html", {
        "weeklies": weeklies,
    })


@login_required
def secretary_weekly_create(request):
    """إنشاء تعديل أسبوعي."""
    _require_secretary(request.user)
    from .models import WeeklySchedule
    from .forms import WeeklyScheduleForm
    from .services_notifications import notify_weekly_schedule_created

    if request.method == "POST":
        form = WeeklyScheduleForm(request.POST)
        if form.is_valid():
            weekly = form.save(commit=False)
            weekly.created_by = request.user
            weekly.status = WeeklySchedule.Status.CONFIRMED
            weekly.save()
            # إشعار المدير
            try:
                notify_weekly_schedule_created(weekly, request.user)
            except Exception:
                pass
            messages.success(request, _("Horaire hebdomadaire créé."))
            return redirect("academics:secretary_weekly_list")
    else:
        form = WeeklyScheduleForm()
    return render(request, "academics/secretary_weekly_form.html", {
        "form": form,
        "is_edit": False,
    })


@login_required
def director_weekly_list(request):
    """قائمة التعديلات الأسبوعية للمدير."""
    _require_director(request.user)
    from .models import WeeklySchedule
    weeklies = (WeeklySchedule.objects
                .select_related("assignment__teacher", "assignment__subject", "created_by")
                .order_by("-week_start"))
    return render(request, "academics/director_weekly_list.html", {
        "weeklies": weeklies,
    })


@login_required
def director_weekly_delete(request, pk):
    """حذف تعديل أسبوعي (المدير فقط)."""
    _require_director(request.user)
    from .models import WeeklySchedule
    w = get_object_or_404(WeeklySchedule, pk=pk)
    if request.method == "POST":
        w.delete()
        messages.success(request, _("Horaire supprimé."))
    return redirect("academics:director_weekly_list")
'''

    if "def secretary_weekly_list" not in content:
        content = content.rstrip() + views + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] Weekly views ajoutées")
    else:
        print("  [=] déjà présentes")


# ============================================================
# 5) Form: WeeklyScheduleForm
# ============================================================
def add_weekly_form():
    path = Path("academics/forms.py")
    content = path.read_text(encoding="utf-8")

    form = '''


class WeeklyScheduleForm(forms.ModelForm):
    """نموذج إنشاء/تعديل جدول أسبوعي."""
    class Meta:
        from .models import WeeklySchedule
        model = WeeklySchedule
        fields = [
            "assignment", "week_start",
            "new_weekday", "new_start_time", "new_duration", "new_teacher",
            "reason",
        ]
        widgets = {
            "week_start": forms.DateInput(attrs={"type": "date"}),
            "new_start_time": forms.TimeInput(attrs={"type": "time"}),
            "reason": forms.Textarea(attrs={"rows": 2}),
        }
'''

    if "class WeeklyScheduleForm" not in content:
        content = content.rstrip() + form + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] WeeklyScheduleForm ajouté")
    else:
        print("  [=] existe déjà")


# ============================================================
# 6) URLs
# ============================================================
def add_weekly_urls():
    path = Path("academics/urls.py")
    content = path.read_text(encoding="utf-8")

    urls = '''    # Horaire hebdomadaire
    path("secretary/weekly/", views.secretary_weekly_list, name="secretary_weekly_list"),
    path("secretary/weekly/new/", views.secretary_weekly_create, name="secretary_weekly_create"),
    path("director/weekly/", views.director_weekly_list, name="director_weekly_list"),
    path("director/weekly/<int:pk>/delete/", views.director_weekly_delete, name="director_weekly_delete"),
'''

    if "secretary_weekly_list" not in content:
        content = content.replace("]\n", urls + "]\n", 1)
        path.write_text(content, encoding="utf-8")
        print("  [+] URLs hebdomadaires ajoutées")
    else:
        print("  [=] déjà présentes")


# ============================================================
# 7) Admin: WeeklySchedule
# ============================================================
def update_admin():
    path = Path("academics/admin.py")
    content = path.read_text(encoding="utf-8")

    if "from .models import Level, Subject, TeachingAssignment, Session, Payslip" in content:
        content = content.replace(
            "from .models import Level, Subject, TeachingAssignment, Session, Payslip",
            "from .models import Level, Subject, TeachingAssignment, Session, Payslip, WeeklySchedule"
        )

    if "@admin.register(WeeklySchedule)" not in content:
        admin_code = '''


@admin.register(WeeklySchedule)
class WeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = ("assignment", "week_start", "effective_weekday", "effective_start_time", "status", "created_by")
    list_filter = ("status", "week_start")
    search_fields = ("assignment__teacher__display_name_fr", "assignment__subject__name_fr")
    readonly_fields = ("created_at", "updated_at")
'''
        content = content.rstrip() + admin_code + "\n"

    path.write_text(content, encoding="utf-8")
    print("  [+] WeeklyScheduleAdmin ajouté")


# ============================================================
# Main
# ============================================================
def main():
    if not Path("manage.py").exists():
        print("ERREUR: manage.py introuvable")
        return

    print("=" * 60)
    print("  UPGRADE WEEKLY — Horaire hebdomadaire")
    print("=" * 60)

    print("\n=== 1) Modèle ===")
    add_weekly_model()
    update_notif_type()

    print("\n=== 2) Notifications ===")
    add_weekly_notification()

    print("\n=== 3) Form ===")
    add_weekly_form()

    print("\n=== 4) Views ===")
    add_weekly_views()

    print("\n=== 5) URLs ===")
    add_weekly_urls()

    print("\n=== 6) Admin ===")
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