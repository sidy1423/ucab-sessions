"""
اختبارات شاملة لتطبيق academics — قواعد العمل الأساسية.
يشمل: النماذج، الخدمات، الصلاحيات، الحسابات.
"""
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from academics.models import Level, Subject, TeachingAssignment, Session
from academics.services import (
    SessionLockedError,
    DuplicateSessionError,
    WorkflowError,
    approve_session,
    compute_all_teachers_hours,
    compute_levels_grand_total,
    compute_levels_summary,
    compute_teacher_hours,
    create_session,
    delete_session,
    reject_session,
    submit_session,
    update_session,
)


class BaseTestSetup(TestCase):
    """إعداد مشترك لكل الاختبارات."""

    @classmethod
    def setUpTestData(cls):
        # المستخدمون
        cls.director = User.objects.create_user(
            username="dir", password="test1234", role=User.Role.DIRECTOR,
            display_name_fr="Directeur Test",
        )
        cls.teacher = User.objects.create_user(
            username="teacher", password="test1234", role=User.Role.TEACHER,
            display_name_fr="Enseignant Test",
        )
        cls.other_teacher = User.objects.create_user(
            username="teacher2", password="test1234", role=User.Role.TEACHER,
            display_name_fr="Autre Enseignant",
        )
        cls.secretary = User.objects.create_user(
            username="sec", password="test1234", role=User.Role.SECRETARY,
        )
        cls.dean = User.objects.create_user(
            username="dean", password="test1234", role=User.Role.DEAN,
        )
        cls.accountant = User.objects.create_user(
            username="acc", password="test1234", role=User.Role.ACCOUNTANT,
        )
        cls.admin_user = User.objects.create_superuser(
            username="admin", password="test1234", email="a@test.com",
        )

        # البيانات الأكاديمية
        cls.level1 = Level.objects.create(name_fr="1ère année", name_ar="السنة الأولى", order=1)
        cls.level2 = Level.objects.create(name_fr="2ème année", name_ar="السنة الثانية", order=2)
        cls.subject = Subject.objects.create(name_fr="Coran", name_ar="القرآن", code="COR")

        # إسناد (الاثنين 08:00)
        cls.assignment = TeachingAssignment.objects.create(
            teacher=cls.teacher,
            subject=cls.subject,
            level=cls.level1,
            weekday=0,
            start_time=time(8, 0),
            duration_hours=2,
            planned_sessions=6,
            created_by=cls.director,
        )


# ============================================================
# 1) اختبارات النماذج الأساسية
# ============================================================
class LevelSubjectTests(BaseTestSetup):
    def test_level_str(self):
        self.assertEqual(str(self.level1), "1ère année")

    def test_subject_str(self):
        self.assertIn("Coran", str(self.subject))
        self.assertIn("COR", str(self.subject))

    def test_assignment_planned_hours(self):
        self.assertEqual(self.assignment.planned_hours, 12)

    def test_assignment_completed_hours_zero_initially(self):
        self.assertEqual(self.assignment.completed_hours, 0)
        self.assertEqual(self.assignment.completed_sessions, 0)

    def test_assignment_remaining_hours(self):
        self.assertEqual(self.assignment.remaining_hours, 12)


# ============================================================
# 2) اختبارات create_session
# ============================================================
class CreateSessionTests(BaseTestSetup):
    def _next_monday(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7
        if days == 0:
            days = 7
        return today + timedelta(days=days)

    def test_create_session_success(self):
        d = self._next_monday()
        s = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=d, topic="Test", notes="",
        )
        self.assertEqual(s.status, Session.Status.DRAFT)
        self.assertEqual(s.teacher, self.teacher)
        self.assertEqual(s.weekday, 0)
        self.assertEqual(s.duration_hours, 2)

    def test_create_session_wrong_teacher(self):
        d = self._next_monday()
        with self.assertRaises(PermissionDenied):
            create_session(
                teacher=self.other_teacher, assignment=self.assignment,
                date=d, topic="Test",
            )

    def test_create_session_wrong_weekday(self):
        today = timezone.localdate()
        wrong_d = today + timedelta(days=((1 - today.weekday()) % 7) or 7)
        with self.assertRaises(ValidationError):
            create_session(
                teacher=self.teacher, assignment=self.assignment,
                date=wrong_d, topic="Test",
            )

    def test_create_session_sunday_rejected(self):
        today = timezone.localdate()
        days_to_sunday = (6 - today.weekday()) % 7
        if days_to_sunday == 0:
            days_to_sunday = 7
        sunday = today + timedelta(days=days_to_sunday)
        with self.assertRaises(ValidationError):
            create_session(
                teacher=self.teacher, assignment=self.assignment,
                date=sunday, topic="Test",
            )

    def test_create_duplicate_session(self):
        d = self._next_monday()
        create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=d, topic="First",
        )
        with self.assertRaises(DuplicateSessionError):
            create_session(
                teacher=self.teacher, assignment=self.assignment,
                date=d, topic="Second",
            )


# ============================================================
# 3) اختبارات Workflow
# ============================================================
class WorkflowTests(BaseTestSetup):
    def setUp(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7 or 7
        self.d = today + timedelta(days=days)
        self.session = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=self.d, topic="Sujet test",
        )

    def test_submit_session(self):
        submit_session(session=self.session, user=self.teacher)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, Session.Status.SUBMITTED)
        self.assertIsNotNone(self.session.submitted_at)

    def test_submit_by_wrong_teacher(self):
        with self.assertRaises(PermissionDenied):
            submit_session(session=self.session, user=self.other_teacher)

    def test_approve_by_director(self):
        submit_session(session=self.session, user=self.teacher)
        approve_session(session=self.session, user=self.director)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, Session.Status.APPROVED)
        self.assertEqual(self.session.reviewed_by, self.director)

    def test_approve_by_teacher_rejected(self):
        submit_session(session=self.session, user=self.teacher)
        with self.assertRaises(PermissionDenied):
            approve_session(session=self.session, user=self.teacher)

    def test_reject_session(self):
        submit_session(session=self.session, user=self.teacher)
        reject_session(session=self.session, user=self.director, reason="خطأ في التاريخ")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, Session.Status.REJECTED)
        self.assertEqual(self.session.rejection_reason, "خطأ في التاريخ")

    def test_reject_requires_reason(self):
        submit_session(session=self.session, user=self.teacher)
        with self.assertRaises(ValidationError):
            reject_session(session=self.session, user=self.director, reason="   ")

    def test_director_can_approve_draft(self):
        """المدير يمكنه اعتماد مسودة مباشرة (سلوك مقصود)."""
        self.assertEqual(self.session.status, Session.Status.DRAFT)
        approve_session(session=self.session, user=self.director)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, Session.Status.APPROVED)

    def test_teacher_cannot_approve_draft(self):
        """المعلم لا يمكنه اعتماد حتى مسودته."""
        with self.assertRaises(PermissionDenied):
            approve_session(session=self.session, user=self.teacher)


# ============================================================
# 4) اختبارات قفل 24 ساعة
# ============================================================
class LockTests(BaseTestSetup):
    def test_lock_deadline(self):
        d = timezone.localdate()
        days_back = ((d.weekday() - 0) % 7) or 7
        past_monday = d - timedelta(days=days_back)
        s = Session(
            assignment=self.assignment, date=past_monday,
            topic="Old", teacher=self.teacher,
            subject=self.subject, level=self.level1,
            weekday=0, start_time=time(8, 0), duration_hours=2,
        )
        s.save()
        self.assertTrue(s.is_locked())

    def test_not_locked_today(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7
        target = today + timedelta(days=days)
        s = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=target, topic="Fresh",
        )
        self.assertFalse(s.is_locked())

    def test_teacher_cannot_edit_locked(self):
        d = timezone.localdate()
        days_back = ((d.weekday() - 0) % 7) or 7
        past_monday = d - timedelta(days=days_back)
        s = Session(
            assignment=self.assignment, date=past_monday,
            topic="Old", teacher=self.teacher,
            subject=self.subject, level=self.level1,
            weekday=0, start_time=time(8, 0), duration_hours=2,
            status=Session.Status.DRAFT,
        )
        s.save()
        with self.assertRaises(SessionLockedError):
            update_session(session=s, user=self.teacher, topic="Modifié")

    def test_director_can_edit_locked(self):
        d = timezone.localdate()
        days_back = ((d.weekday() - 0) % 7) or 7
        past_monday = d - timedelta(days=days_back)
        s = Session(
            assignment=self.assignment, date=past_monday,
            topic="Old", teacher=self.teacher,
            subject=self.subject, level=self.level1,
            weekday=0, start_time=time(8, 0), duration_hours=2,
            status=Session.Status.APPROVED,
        )
        s.save()
        update_session(session=s, user=self.director, topic="Corrigé")
        s.refresh_from_db()
        self.assertEqual(s.topic, "Corrigé")


# ============================================================
# 5) اختبارات حساب الساعات
# ============================================================
class HoursComputationTests(BaseTestSetup):
    def setUp(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7 or 7
        self.d1 = today + timedelta(days=days)
        self.d2 = self.d1 + timedelta(days=7)

    def test_completed_only_approved(self):
        s1 = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=self.d1, topic="A",
        )
        hours = compute_teacher_hours(teacher=self.teacher)
        self.assertEqual(hours.total_hours, 0)

        submit_session(session=s1, user=self.teacher)
        approve_session(session=s1, user=self.director)

        hours = compute_teacher_hours(teacher=self.teacher)
        self.assertEqual(hours.total_hours, 2)

    def test_rejected_not_counted(self):
        s1 = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=self.d1, topic="A",
        )
        submit_session(session=s1, user=self.teacher)
        reject_session(session=s1, user=self.director, reason="خطأ")

        hours = compute_teacher_hours(teacher=self.teacher)
        self.assertEqual(hours.total_hours, 0)

    def test_hours_by_level(self):
        s1 = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=self.d1, topic="A",
        )
        submit_session(session=s1, user=self.teacher)
        approve_session(session=s1, user=self.director)

        hours = compute_teacher_hours(teacher=self.teacher)
        self.assertIn(self.level1.id, hours.by_level)
        self.assertEqual(hours.by_level[self.level1.id]["hours"], 2)

    def test_hours_date_filter(self):
        s1 = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=self.d1, topic="A",
        )
        submit_session(session=s1, user=self.teacher)
        approve_session(session=s1, user=self.director)

        hours = compute_teacher_hours(
            teacher=self.teacher,
            date_from=self.d2,
        )
        self.assertEqual(hours.total_hours, 0)

        hours = compute_teacher_hours(
            teacher=self.teacher,
            date_from=self.d1,
            date_to=self.d2,
        )
        self.assertEqual(hours.total_hours, 2)


# ============================================================
# 6) اختبارات الإجماليات
# ============================================================
class GrandTotalTests(BaseTestSetup):
    def test_grand_total_no_sessions(self):
        g = compute_levels_grand_total()
        self.assertEqual(g["planned_hours"], 12)
        self.assertEqual(g["completed_hours"], 0)
        self.assertEqual(g["remaining_hours"], 12)

    def test_grand_total_after_approval(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7 or 7
        d = today + timedelta(days=days)
        s = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=d, topic="A",
        )
        submit_session(session=s, user=self.teacher)
        approve_session(session=s, user=self.director)

        g = compute_levels_grand_total()
        self.assertEqual(g["completed_hours"], 2)
        self.assertEqual(g["remaining_hours"], 10)
        self.assertEqual(g["percent"], 17)


# ============================================================
# 7) اختبارات الحذف
# ============================================================
class DeleteTests(BaseTestSetup):
    def setUp(self):
        today = timezone.localdate()
        days = (0 - today.weekday()) % 7 or 7
        self.session = create_session(
            teacher=self.teacher, assignment=self.assignment,
            date=today + timedelta(days=days), topic="A",
        )

    def test_only_superuser_can_delete(self):
        with self.assertRaises(PermissionDenied):
            delete_session(session=self.session, user=self.director)
        with self.assertRaises(PermissionDenied):
            delete_session(session=self.session, user=self.teacher)

    def test_superuser_can_delete(self):
        sid = self.session.id
        delete_session(session=self.session, user=self.admin_user)
        self.assertFalse(Session.objects.filter(id=sid).exists())


# ============================================================
# 8) اختبارات الصلاحيات في Views
# ============================================================
class ViewPermissionTests(BaseTestSetup):
    def test_teacher_dashboard_requires_teacher(self):
        self.client.login(username="dir", password="test1234")
        response = self.client.get("/teacher/")
        self.assertEqual(response.status_code, 403)

    def test_director_dashboard_requires_director(self):
        self.client.login(username="teacher", password="test1234")
        response = self.client.get("/director/")
        self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_requires_superuser(self):
        self.client.login(username="dir", password="test1234")
        response = self.client.get("/admin-panel/")
        self.assertEqual(response.status_code, 403)

    def test_teacher_accesses_own_dashboard(self):
        self.client.login(username="teacher", password="test1234")
        response = self.client.get("/teacher/")
        self.assertEqual(response.status_code, 200)