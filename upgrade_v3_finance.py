"""
upgrade_v3_finance.py — نظام كشوف الرواتب الشهرية
=================================================
- نموذج Payslip (كشف راتب شهري)
- حالة الدفع (pending/paid)
- لوحة العميد المالية
- تحديث لوحة المحاسب
"""

from pathlib import Path


# ============================================================
# 1) نموذج Payslip
# ============================================================
def add_payslip_model():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    payslip = '''


class Payslip(models.Model):
    """
    Fiche de paie mensuelle pour un enseignant.
    Calculée à partir des séances approuvées dans le mois.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente de paiement")
        PAID = "paid", _("Payé")

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="payslips", verbose_name=_("Enseignant"),
    )
    year = models.PositiveIntegerField(_("Année"))
    month = models.PositiveIntegerField(_("Mois (1-12)"))
    total_hours = models.DecimalField(
        _("Total heures"), max_digits=10, decimal_places=2, default=0,
    )
    total_amount = models.DecimalField(
        _("Montant total (FCFA)"), max_digits=12, decimal_places=2, default=0,
    )
    status = models.CharField(
        _("Statut"), max_length=20,
        choices=Status.choices, default=Status.PENDING,
    )
    paid_at = models.DateTimeField(_("Payé le"), null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="paid_payslips",
        verbose_name=_("Payé par"),
    )
    notes = models.TextField(_("Notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month", "teacher__display_name_fr"]
        verbose_name = _("Fiche de paie")
        verbose_name_plural = _("Fiches de paie")
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "year", "month"],
                name="uniq_payslip_teacher_month",
            )
        ]
        indexes = [
            models.Index(fields=["year", "month", "status"]),
        ]

    def __str__(self):
        return f"{self.teacher} - {self.month:02d}/{self.year} - {self.total_amount} FCFA [{self.get_status_display()}]"

    @property
    def period_label(self):
        """عرض الشهر بالاسم."""
        months_fr = [
            "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
        ]
        return f"{months_fr[self.month]} {self.year}"
'''

    if "class Payslip" not in content:
        content = content.rstrip() + payslip + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] Payslip model ajouté")
    else:
        print("  [=] Payslip existe déjà")


# ============================================================
# 2) خدمات الرواتب
# ============================================================
def add_payslip_services():
    path = Path("academics/services.py")
    content = path.read_text(encoding="utf-8")

    services = '''


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
'''

    if "def generate_payslip" not in content:
        content = content.rstrip() + services + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] generate_payslip, mark_payslip_as_paid ajoutées")
    else:
        print("  [=] déjà présents")


# ============================================================
# 3) إشعارات الدفع
# ============================================================
def add_payment_notifications():
    path = Path("academics/services_notifications.py")
    content = path.read_text(encoding="utf-8")

    notif = '''


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
'''

    if "notify_payslip_paid" not in content:
        content = content.rstrip() + notif + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] notify_payslip_paid ajoutée")
    else:
        print("  [=] déjà présente")


# ============================================================
# 4) Notification.Type — إضافة PAYSLIP_PAID
# ============================================================
def update_notification_type():
    path = Path("academics/models.py")
    content = path.read_text(encoding="utf-8")

    old = '''        ASSIGNMENT_CREATED = "assignment_created", _("Affectation créée")'''

    new = '''        ASSIGNMENT_CREATED = "assignment_created", _("Affectation créée")
        PAYSLIP_PAID = "payslip_paid", _("Fiche de paie payée")'''

    if old in content and "PAYSLIP_PAID" not in content:
        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        print("  [+] Notification.Type.PAYSLIP_PAID ajouté")
    else:
        print("  [=] déjà présent ou pattern différent")


# ============================================================
# 5) Views — payslips للـ accountant + dean + director
# ============================================================
def add_payslip_views():
    path = Path("academics/views.py")
    content = path.read_text(encoding="utf-8")

    new_views = '''


# ================= Payslips (Fiches de paie) =================
@login_required
def accountant_payslips(request):
    """لوحة المحاسب — كشوف الرواتب."""
    _require_accountant(request.user)
    from datetime import date
    from .models import Payslip
    from .services import generate_monthly_payslips

    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    # توليد الكشوف (إذا لم تكن موجودة)
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

    total_paid = sum(
        p.total_amount for p in payslips if p.status == Payslip.Status.PAID
    )
    total_pending = sum(
        p.total_amount for p in payslips if p.status == Payslip.Status.PENDING
    )

    return render(request, "academics/accountant_payslips.html", {
        "payslips": payslips,
        "year": year,
        "month": month,
        "total_paid": total_paid,
        "total_pending": total_pending,
    })


@login_required
def accountant_payslip_mark_paid(request, pk):
    """تأكيد دفع كشف راتب."""
    _require_accountant(request.user)
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
    """إرجاع كشف إلى حالة الانتظار (تصحيح)."""
    _require_accountant(request.user)
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
    """لوحة العميد — الحالة المالية."""
    _require_dean(request.user)
    from datetime import date
    from .models import Payslip
    from django.db.models import Sum, Count

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
'''

    if "def accountant_payslips" not in content:
        content = content.rstrip() + new_views + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] views payslips ajoutées")
    else:
        print("  [=] déjà présents")


# ============================================================
# 6) URLs
# ============================================================
def update_urls():
    path = Path("academics/urls.py")
    content = path.read_text(encoding="utf-8")

    new_urls = '''    # Fiches de paie
    path("accountant/payslips/", views.accountant_payslips, name="accountant_payslips"),
    path("accountant/payslips/<int:pk>/paid/", views.accountant_payslip_mark_paid, name="accountant_payslip_mark_paid"),
    path("accountant/payslips/<int:pk>/pending/", views.accountant_payslip_mark_pending, name="accountant_payslip_mark_pending"),

    # Finances du doyen
    path("dean/finances/", views.dean_finances, name="dean_finances"),
'''

    if "accountant_payslips" not in content:
        content = content.replace("]\n", new_urls + "]\n", 1)
        path.write_text(content, encoding="utf-8")
        print("  [+] URLs ajoutées")
    else:
        print("  [=] déjà présentes")


# ============================================================
# 7) Admin — تسجيل Payslip
# ============================================================
def update_admin():
    path = Path("academics/admin.py")
    content = path.read_text(encoding="utf-8")

    if "Payslip" not in content.split("from .models import")[1].split("\n")[0]:
        content = content.replace(
            "from .models import Level, Subject, TeachingAssignment, Session",
            "from .models import Level, Subject, TeachingAssignment, Session, Payslip",
        )

    if "@admin.register(Payslip)" not in content:
        admin_code = '''


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("teacher", "year", "month", "total_hours", "total_amount", "status", "paid_at")
    list_filter = ("status", "year", "month")
    search_fields = ("teacher__display_name_fr",)
    readonly_fields = ("created_at", "updated_at", "paid_at")
'''

        content = content.rstrip() + admin_code + "\n"
        path.write_text(content, encoding="utf-8")
        print("  [+] PayslipAdmin ajouté")
    else:
        print("  [=] déjà présent")


# ============================================================
# Main
# ============================================================
def main():
    if not Path("manage.py").exists():
        print("ERREUR: manage.py introuvable")
        return

    print("=" * 60)
    print("  UPGRADE V3 — Finances & Payslips")
    print("=" * 60)

    print("\n=== 1) Modèles ===")
    add_payslip_model()
    update_notification_type()

    print("\n=== 2) Services ===")
    add_payslip_services()
    add_payment_notifications()

    print("\n=== 3) Views ===")
    add_payslip_views()

    print("\n=== 4) URLs ===")
    update_urls()

    print("\n=== 5) Admin ===")
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