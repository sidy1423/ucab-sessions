from django import forms
from .models import Session, TeachingAssignment


class SessionForm(forms.ModelForm):
    """نموذج توثيق حصة (معلم)."""
    class Meta:
        model = Session
        fields = ["assignment", "date", "topic", "notes"]
        widgets = {
            "date":  forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher is not None:
            self.fields["assignment"].queryset = TeachingAssignment.objects.filter(teacher=teacher)


class SessionEditForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ["topic", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class RejectForm(forms.Form):
    reason = forms.CharField(
        label="Motif de rejet",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = TeachingAssignment
        fields = ["teacher", "subject", "level", "weekday", "start_time",
                  "duration_hours", "planned_sessions"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"})}


class WeeklyScheduleForm(forms.ModelForm):
    """نموذج إنشاء/تعديل جدول أسبوعي."""
    class Meta:
        from .models import WeeklySchedule
        model = WeeklySchedule
        fields = [
            "assignment", "week_start",
            "new_weekday", "new_start_time", "new_duration", "new_teacher",
            "reason",
        ]
        widgets = {
            "week_start": forms.DateInput(attrs={"type": "date"}),
            "new_start_time": forms.TimeInput(attrs={"type": "time"}),
            "reason": forms.Textarea(attrs={"rows": 2}),
        }

