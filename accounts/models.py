"""مستخدم مخصص بـ 6 أدوار: معلم، سكرتير، مدير الدراسات، عميد، محاسب، مدير النظام."""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Role(models.TextChoices):
        TEACHER    = "teacher",    _("Enseignant")
        SECRETARY  = "secretary",  _("Secrétaire")
        DIRECTOR   = "director",   _("Directeur des études")
        DEAN       = "dean",       _("Doyen")
        ACCOUNTANT = "accountant", _("Comptable")

    role = models.CharField(_("Rôle"), max_length=20,
                            choices=Role.choices, default=Role.TEACHER)
    display_name_fr = models.CharField(_("Nom en français"), max_length=150, blank=True)
    display_name_ar = models.CharField(_("الاسم بالعربية"), max_length=150, blank=True)

    class Meta:
        verbose_name = _("Utilisateur")
        verbose_name_plural = _("Utilisateurs")

    def __str__(self):
        return self.display_name_fr or self.get_full_name() or self.username

    # ---------- مساعدات الصلاحيات ----------
    @property
    def is_teacher(self):    return self.role == self.Role.TEACHER
    @property
    def is_secretary(self):  return self.role == self.Role.SECRETARY
    @property
    def is_director(self):   return self.role == self.Role.DIRECTOR
    @property
    def is_dean(self):       return self.role == self.Role.DEAN
    @property
    def is_accountant(self): return self.role == self.Role.ACCOUNTANT

    @property
    def is_admin_user(self):
        """مدير النظام = superuser فقط."""
        return self.is_superuser