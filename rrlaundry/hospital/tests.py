from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import (
    HospitalStaffProfile, LaundryWorkerProfile, Role,
)
from core.test_factories import (
    make_hospital_profile, make_laundry_profile, make_user,
)


# Disable manifest storage during view tests so Jinja2 static() calls don't
# require a fully built staticfiles.json in CI or fresh checkouts.
_SIMPLE_STORAGE = override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
)


# ─── Hospital portal — unauthenticated & wrong-role denials ──────────────────

@_SIMPLE_STORAGE
class HospitalPortalAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.head_user = make_user('head@access.com', Role.HOSPITAL_HEAD, is_onboarded=True)
        self.hospital  = make_hospital_profile(self.head_user)

        self.laundry_user  = make_user('ladmin@access.com', Role.LAUNDRY_ADMIN,  is_onboarded=True)
        self.delivery_user = make_user('deliv@access.com',  Role.DELIVERY_PARTNER, is_onboarded=True)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get(reverse('hospital_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_laundry_admin_denied_hospital_dashboard(self):
        self.client.force_login(self.laundry_user)
        resp = self.client.get(reverse('hospital_dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_delivery_partner_denied_hospital_dashboard(self):
        self.client.force_login(self.delivery_user)
        resp = self.client.get(reverse('hospital_dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_hospital_head_can_access_dashboard(self):
        self.client.force_login(self.head_user)
        resp = self.client.get(reverse('hospital_dashboard'))
        self.assertEqual(resp.status_code, 200)


# ─── Hospital portal — head-only view restrictions ───────────────────────────

@_SIMPLE_STORAGE
class HospitalHeadOnlyViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.head_user = make_user('head2@access.com', Role.HOSPITAL_HEAD, is_onboarded=True)
        self.hospital  = make_hospital_profile(self.head_user)

        self.staff_user = make_user('staff@access.com', Role.HOSPITAL_STAFF, is_onboarded=True)
        HospitalStaffProfile.objects.create(
            user=self.staff_user,
            hospital=self.hospital,
            phone_number='9000000099',
        )

    def test_hospital_staff_denied_partner_selection(self):
        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse('hospital_partners'))
        self.assertEqual(resp.status_code, 403)

    def test_hospital_head_can_access_partner_selection(self):
        self.client.force_login(self.head_user)
        resp = self.client.get(reverse('hospital_partners'))
        # 200 — head has profile and the correct role
        self.assertEqual(resp.status_code, 200)


# ─── Laundry portal — unauthenticated & wrong-role denials ───────────────────

@_SIMPLE_STORAGE
class LaundryPortalAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = make_user('ladmin2@access.com', Role.LAUNDRY_ADMIN, is_onboarded=True)
        self.laundry    = make_laundry_profile(self.admin_user)

        self.worker_user = make_user('lworker@access.com', Role.LAUNDRY_WORKER, is_onboarded=True)
        LaundryWorkerProfile.objects.create(
            user=self.worker_user,
            laundry=self.laundry,
            phone_number='9000000088',
        )
        self.hospital_user = make_user('hosp3@access.com', Role.HOSPITAL_HEAD, is_onboarded=True)

    def test_unauthenticated_redirects_from_laundry_dashboard(self):
        resp = self.client.get(reverse('laundry_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_hospital_role_denied_laundry_dashboard(self):
        self.client.force_login(self.hospital_user)
        resp = self.client.get(reverse('laundry_dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_laundry_worker_denied_pricing_view(self):
        # PricingView has laundry_admin_only = True
        self.client.force_login(self.worker_user)
        resp = self.client.get(reverse('laundry_pricing'))
        self.assertEqual(resp.status_code, 403)

    def test_laundry_admin_can_access_pricing_view(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse('laundry_pricing'))
        self.assertEqual(resp.status_code, 200)

    def test_laundry_admin_can_access_dashboard(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse('laundry_dashboard'))
        self.assertEqual(resp.status_code, 200)
