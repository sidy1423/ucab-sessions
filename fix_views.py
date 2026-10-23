"""
fix_views.py — إصلاح accountant_payslips بدون تدخل يدوي
يستبدل الدالة كاملة (من `def accountant_payslips` إلى الدالة التالية)
بنص صحيح.
"""
import re
from pathlib import Path

path = Path("academics/views.py")
content = path.read_text(encoding="utf-8")

# ============================================================
# 1) تحديد دالة accountant_payslips الكاملة واستبدالها
# ============================================================
# نبحث من "@login_required\ndef accountant_payslips" إلى قبل "@login_required" التالي

pattern = r"@login_required\ndef accountant_payslips\(request\):.*?(?=\n@login_required|\n# ==========|\n\ndef _|\Z)"

new_func = '''@login_required
def accountant_payslips(request):
    """لوحة المحاسب — كشوف الرواتب.
    متاحة للمحاسب + المدير + العميد + الأدمين.
    """
    if not (request.user.is_accountant or request.user.is_director 
            or request.user.is_dean or request.user.is_admin_user):
        raise PermissionDenied(_("Page réservée au comptable, directeur, doyen ou administrateur."))
    
    from datetime import date
    from .models import Payslip
    from .services import generate_monthly_payslips

    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    # توليد الكشوف
    if request.method == "POST" and request.POST.get("action") == "generate":
        try:
            generate_monthly_payslips(year=year, month=month)
            messages.success(request, _("Fiches générées."))
        except Exception as e:
            messages.error(request, str(e))
        return redirect(f"{request.path}?year={year}&month={month}")

    payslips = Payslip.objects.filter(year=year, month=month).select_related(
        "teacher", "paid_by",
    ).order_by("teacher__display_name_fr")

    total_paid = sum(
        p.total_amount for p in payslips if p.status == Payslip.Status.PAID
    )
    total_pending = sum(
        p.total_amount for p in payslips if p.status == Payslip.Status.PENDING
    )

    return render(request, "academics/accountant_payslips.html", {
        "payslips": payslips,
        "year": year,
        "month": month,
        "total_paid": total_paid,
        "total_pending": total_pending,
    })
'''

if re.search(pattern, content, flags=re.DOTALL):
    content = re.sub(pattern, new_func, content, count=1, flags=re.DOTALL)
    print("  [+] accountant_payslips corrigée")
else:
    print("  [!] pattern accountant_payslips introuvable")

# ============================================================
# 2) تحقق: teacher_session_create سليمة؟
# ============================================================
if "def teacher_session_create" not in content:
    print("  [!] teacher_session_create MANQUANTE — on la rajoute")
    # أضفها قبل accountant_payslips
    missing_func = '''


@login_required
def teacher_session_create(request):
    _require_teacher(request.user)
    if request.method == "POST":
        form = SessionForm(request.POST, teacher=request.user)
        if form.is_valid():
            try:
                create_session(
                    teacher=request.user,
                    assignment=form.cleaned_data["assignment"],
                    date=form.cleaned_data["date"],
                    topic=form.cleaned_data["topic"],
                    notes=form.cleaned_data.get("notes", ""),
                )
                messages.success(request, _("Séance enregistrée comme brouillon."))
                return redirect("academics:teacher_dashboard")
            except Exception as e:
                form.add_error(None, str(e))
    else:
        form = SessionForm(teacher=request.user)
    return render(request, "academics/session_form.html", {"form": form, "is_edit": False})
'''
    # أضفها قبل accountant_payslips
    marker = "# ================= Payslips (Fiches de paie) ================="
    if marker in content:
        content = content.replace(marker, missing_func + "\n\n" + marker)
        print("  [+] teacher_session_create réajoutée")
else:
    print("  [=] teacher_session_create existe déjà")

# ============================================================
# 3) تحقق: هل هناك كود مكسور من create_session في accountant_payslips؟
# ============================================================
# نبحث عن أي create_session داخل accountant_payslips
accountant_section = re.search(
    r"def accountant_payslips\(request\):(.*?)(?=\n@login_required|\Z)",
    content, flags=re.DOTALL
)
if accountant_section:
    section = accountant_section.group(1)
    if "create_session" in section:
        print("  [!] كود مكسور موجود في accountant_payslips — نصلحه")
        # احذف أي سطر فيه create_session
        new_section = re.sub(
            r"\s*if form\.is_valid\(\):.*?form\.add_error\(None, str\(e\)\)",
            "",
            section, flags=re.DOTALL
        )
        content = content.replace(section, new_section)
        print("  [+] كود مكسور محذوف")
    else:
        print("  [=] accountant_payslips نظيفة")

# ============================================================
# 4) كتابة الملف
# ============================================================
path.write_text(content, encoding="utf-8")
print("\n  [✓] الملف محفوظ")

# ============================================================
# 5) تحقق من صحة Python syntax
# ============================================================
try:
    import ast
    ast.parse(content)
    print("  [✓] Syntax OK")
except SyntaxError as e:
    print(f"  [✗] Syntax Error at line {e.lineno}: {e.msg}")
    print(f"      {e.text}")

print("\n  Prochaine étape: python manage.py check")
