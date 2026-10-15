"""تسجيل الدخول والخروج."""
import logging
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from .forms import RoleLoginForm

logger = logging.getLogger(__name__)


class RoleLoginView(LoginView):
    template_name = "accounts/login.html"
    form_class = RoleLoginForm
    redirect_authenticated_user = True

    def form_invalid(self, form):
        logger.warning(
            "Login failed. Errors: %s | Data: %s",
            form.errors.as_json(),
            {k: str(v) for k, v in form.data.items() if k != 'csrfmiddlewaretoken'}
        )
        return super().form_invalid(form)

    def get_success_url(self):
        user = self.request.user
        # الأدمين (superuser) → لوحته الخاصة
        if user.is_superuser:
            return reverse_lazy("academics:admin_dashboard")
        if user.is_director:   return reverse_lazy("academics:director_dashboard")
        if user.is_secretary:  return reverse_lazy("academics:secretary_dashboard")
        if user.is_dean:       return reverse_lazy("academics:dean_dashboard")
        if user.is_accountant: return reverse_lazy("academics:accountant_dashboard")
        return reverse_lazy("academics:teacher_dashboard")


def logout_view(request):
    logout(request)
    return redirect("accounts:login")
