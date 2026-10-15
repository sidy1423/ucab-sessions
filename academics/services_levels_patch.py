def compute_levels_totals(*, date_from=None, date_to=None):
    """
    مجموع الساعات المعتمدة لكل مستوى، مع احترام فلترة التاريخ.
    """
    from django.db.models import Q
    qs = Session.objects.filter(status=Session.Status.APPROVED)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    rows = (qs.values("level_id", "level__name_fr")
              .annotate(hours=Sum("duration_hours"), sessions=Count("id"))
              .order_by("level__name_fr"))
    return {r["level_id"]: {"name": r["level__name_fr"],
                            "hours": r["hours"] or 0,
                            "sessions": r["sessions"]} for r in rows}
