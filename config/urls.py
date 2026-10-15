from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),   # لتبديل اللغة
]

urlpatterns += i18n_patterns(
    path("", include("accounts.urls")),
    path("", include("academics.urls")),
    prefix_default_language=False,
)