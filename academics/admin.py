from django.contrib import admin
from .models import Level, Subject, TeachingAssignment, Session, Payslip, WeeklySchedule

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name_fr", "name_ar", "order", "hourly_rate")
    list_editable = ("hourly_rate",)
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


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("teacher", "year", "month", "total_hours", "total_amount", "status", "paid_at")
    list_filter = ("status", "year", "month")
    search_fields = ("teacher__display_name_fr",)
    readonly_fields = ("created_at", "updated_at", "paid_at")


@admin.register(WeeklySchedule)
class WeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = ("assignment", "week_start", "effective_weekday", "effective_start_time", "status", "created_by")
    list_filter = ("status", "week_start")
    search_fields = ("assignment__teacher__display_name_fr", "assignment__subject__name_fr")
    readonly_fields = ("created_at", "updated_at")

