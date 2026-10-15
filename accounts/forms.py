"""نموذج تسجيل دخول بسيط — username نصي، بدون قوائم."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class RoleLoginForm(AuthenticationForm):
    """نموذج دخول بسيط: يُدخل المستخدم اسمه يدويًا."""
    username = forms.CharField(
        label=_("Nom d'utilisateur"),
        widget=forms.TextInput(attrs={
            "placeholder": "director1 / teacher1 / ...",
            "autocomplete": "off",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label=_("Mot de passe"),
        widget=forms.PasswordInput(attrs={"autocomplete": "off"}),
    )
