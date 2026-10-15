from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Rôle & noms", {"fields": ("role", "display_name_fr", "display_name_ar")}),
    )
    list_display = ("username", "display_name_fr", "role", "is_staff", "is_superuser")
    list_filter  = ("role", "is_staff", "is_superuser")