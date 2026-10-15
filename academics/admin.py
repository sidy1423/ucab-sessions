from django.contrib import admin
from .models import Level, Subject, TeachingAssignment, Session

admin.site.register(Level)
admin.site.register(Subject)


@admin.register(TeachingAssignment)
class TeachingAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "level", "weekday", "start_time",
                    "planned_sessions", "completed_sessions", "remaining_sessions")
    list_filter  = ("level", "subject", "weekday")
    search_fields = ("teacher__display_name_fr", "subject__name_fr")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "level", "date", "start_time",
                    "duration_hours", "status", "reviewed_by", "locked_at")
    list_filter  = ("status", "level", "subject")
    search_fields = ("teacher__display_name_fr", "topic")
    readonly_fields = ("created_at", "updated_at", "locked_at")