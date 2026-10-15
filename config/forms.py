"""نموذج تسجيل دخول موحّد: يختار المستخدم اسمه من قائمة حسب الدور."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import User


class RoleLoginForm(AuthenticationForm):
    username = forms.ModelChoiceField(
        queryset=User.objects.all().order_by("role", "display_name_fr", "username"),
        label=_("Nom d'utilisateur"),
        empty_label=_("— Choisissez votre nom —"),
    )

    def label_from_instance(self, obj):
        return f"{obj.get_role_display()} — {obj}"