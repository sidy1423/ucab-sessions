"""النماذج الأكاديمية: المستوى، المادة، الإسناد، الحصة."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Level(models.Model):
    """Niveau / المستوى الدراسي."""
    name_fr = models.CharField(_("Nom (français)"), max_length=100, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=100, unique=True)
    order   = models.PositiveIntegerField(_("Ordre"), default=0)

    class Meta:
        ordering = ["order", "name_fr"]
        verbose_name = _("Niveau")
        verbose_name_plural = _("Niveaux")

    def __str__(self):
        return self.name_fr


class Subject(models.Model):
    """Matière / المادة."""
    name_fr = models.CharField(_("Nom (français)"), max_length=150)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=150)
    code    = models.CharField(_("Code"), max_length=20, unique=True)

    class Meta:
        verbose_name = _("Matière")
        verbose_name_plural = _("Matières")

    def __str__(self):
        return f"{self.name_fr} ({self.code})"


class TeachingAssignment(models.Model):
    """
    Affectation : enseignant -> matière -> niveau -> jour -> heure.
    Le directeur ou le secrétaire crée l'affectation.
    planned_sessions = nombre total de séances prévues pour cette matière.
    """

    class Weekday(models.IntegerChoices):
        MONDAY    = 0, _("Lundi")
        TUESDAY   = 1, _("Mardi")
        WEDNESDAY = 2, _("Mercredi")
        THURSDAY  = 3, _("Jeudi")
        FRIDAY    = 4, _("Vendredi")
        SATURDAY  = 5, _("Samedi")

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        limit_choices_to={"role": "teacher"},
        related_name="assignments", verbose_name=_("Enseignant"),
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, verbose_name=_("Matière"))
    level   = models.ForeignKey(Level,   on_delete=models.PROTECT, verbose_name=_("Niveau"))
    weekday = models.PositiveSmallIntegerField(_("Jour"), choices=Weekday.choices)
    start_time = models.TimeField(_("Heure de début"))
    duration_hours = models.PositiveSmallIntegerField(_("Durée (heures)"), default=2)

    # ---- عدد الحصص المخططة للمادة (مثال: 6 حصص × 2 ساعة = 12 ساعة) ----
    planned_sessions = models.PositiveIntegerField(
        _("Nombre de séances prévues"), default=0,
        help_text=_("Nombre total de séances prévues pour cette matière."),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_assignments",
        verbose_name=_("Créé par"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Affectation")
        verbose_name_plural = _("Affectations")
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "subject", "level", "weekday", "start_time"],
                name="uniq_assignment_slot",
            )
        ]

    def clean(self):
        if self.weekday not in (0, 1, 2, 3, 4, 5):
            raise ValidationError(_("Les jours d'étude vont du lundi au samedi."))

    def __str__(self):
        return f"{self.teacher} - {self.subject} ({self.level}) - {self.get_weekday_display()} {self.start_time}"

    # ---------- حساب الساعات ----------
    @property
    def planned_hours(self):
        """الساعات الكلية المخططة = عدد الحصص × مدة الحصة."""
        return self.planned_sessions * self.duration_hours

    @property
    def completed_sessions(self):
        """عدد الحصص المعتمدة فقط."""
        return self.sessions.filter(status=Session.Status.APPROVED).count()

    @property
    def completed_hours(self):
        """الساعات المنجزة = الحصص المعتمدة × مدة الحصة."""
        return self.completed_sessions * self.duration_hours

    @property
    def remaining_sessions(self):
        return max(0, self.planned_sessions - self.completed_sessions)

    @property
    def remaining_hours(self):
        return max(0, self.planned_hours - self.completed_hours)

    @property
    def progress_percent(self):
        if self.planned_sessions == 0:
            return 0
        return round(100 * self.completed_sessions / self.planned_sessions)


class Session(models.Model):
    """
    Séance documentée / حصة موثّقة.

    Workflow:
        draft -> submitted -> approved | rejected
    Seules les séances 'approved' comptent dans les heures.
    Après 24h de la fin, l'enseignant ne peut plus modifier.
    """

    class Status(models.TextChoices):
        DRAFT     = "draft",     _("Brouillon")
        SUBMITTED = "submitted", _("En attente de validation")
        APPROVED  = "approved",  _("Approuvée")
        REJECTED  = "rejected",  _("Rejetée")

    assignment = models.ForeignKey(
        TeachingAssignment, on_delete=models.PROTECT,
        related_name="sessions", verbose_name=_("Affectation"),
    )
    date  = models.DateField(_("Date de la séance"), default=timezone.localdate)
    topic = models.CharField(_("Sujet étudié"), max_length=255)
    notes = models.TextField(_("Remarques"), blank=True)

    # Snapshot
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="sessions")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="sessions")
    level   = models.ForeignKey(Level,   on_delete=models.PROTECT, related_name="sessions")
    weekday = models.PositiveSmallIntegerField(_("Jour"))
    start_time = models.TimeField(_("Heure de début"))
    duration_hours = models.PositiveSmallIntegerField(_("Heures"), default=2)

    # ---- Workflow ----
    status = models.CharField(
        _("Statut"), max_length=20,
        choices=Status.choices, default=Status.DRAFT,
    )
    submitted_at = models.DateTimeField(_("Envoyée à"), null=True, blank=True)
    reviewed_at  = models.DateTimeField(_("Révisée à"), null=True, blank=True)
    reviewed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewed_sessions",
        verbose_name=_("Révisée par"),
    )
    rejection_reason = models.TextField(_("Motif de rejet"), blank=True)

    # ---- Traçabilité ----
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="edited_sessions",
        verbose_name=_("Dernière modification par"),
    )
    locked_at  = models.DateTimeField(_("Verrouillé à"), null=True, blank=True)

    class Meta:
        ordering = ["-date", "-start_time"]
        verbose_name = _("Séance")
        verbose_name_plural = _("Séances")
        indexes = [
            models.Index(fields=["teacher", "date"]),
            models.Index(fields=["level", "date"]),
            models.Index(fields=["status"]),
        ]

    # ---------- Business rules ----------
    @property
    def session_end(self):
        start_dt = timezone.make_aware(
            timezone.datetime.combine(self.date, self.start_time),
            timezone.get_current_timezone(),
        )
        return start_dt + timedelta(hours=self.duration_hours)

    @property
    def lock_deadline(self):
        return self.session_end + timedelta(hours=24)

    def is_locked(self):
        return timezone.now() > self.lock_deadline

    @property
    def is_editable_by_teacher(self):
        """المعلم يمكنه التعديل فقط قبل القفل وفي حالة draft/rejected."""
        if self.is_locked():
            return False
        return self.status in (self.Status.DRAFT, self.Status.REJECTED)

    def clean(self):
        if self.date:
            if self.date.weekday() > 5:
                raise ValidationError(_("Pas de séance le dimanche."))
            if self.weekday is not None and self.date.weekday() != self.weekday:
                raise ValidationError(_("Le jour de la date ne correspond pas à l'affectation."))

    def save(self, *args, **kwargs):
        if not self.pk and self.assignment_id:
            a = self.assignment
            self.teacher_id = a.teacher_id
            self.subject_id = a.subject_id
            self.level_id   = a.level_id
            self.weekday    = a.weekday
            self.start_time = a.start_time
            self.duration_hours = a.duration_hours
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher} - {self.subject} - {self.date} [{self.get_status_display()}]"


"""نموذج الإشعارات."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """
    إشعار لمستخدم معين.
    أنواع الإشعارات:
        - session_submitted: معلم أرسل حصة → للمدير
        - session_approved: مدير اعتمد حصة → للمعلم
        - session_rejected: مدير رفض حصة → للمعلم
        - session_deleted: حذف حصة → للمعلم
    """

    class Type(models.TextChoices):
        SESSION_SUBMITTED = "session_submitted", _("Séance envoyée")
        SESSION_APPROVED  = "session_approved",  _("Séance approuvée")
        SESSION_REJECTED  = "session_rejected",  _("Séance rejetée")
        SESSION_DELETED   = "session_deleted",   _("Séance supprimée")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications", verbose_name=_("Destinataire"),
    )
    type = models.CharField(_("Type"), max_length=30, choices=Type.choices)
    message = models.CharField(_("Message"), max_length=500)
    url = models.CharField(_("Lien"), max_length=300, blank=True)
    is_read = models.BooleanField(_("Lu"), default=False)
    created_at = models.DateTimeField(_("Créé le"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"{self.recipient} — {self.get_type_display()} — {self.created_at:%Y-%m-%d %H:%M}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])
