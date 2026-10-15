"""Context processor لإشعارات غير المقروءة في كل صفحة."""
from django.utils.translation import gettext_lazy as _
from .models import Notification


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_count": 0, "recent_notifications": []}

    qs = Notification.objects.filter(recipient=request.user, is_read=False)
    return {
        "unread_count": qs.count(),
        "recent_notifications": qs[:5],
    }
