"""
Idempotent demo data seed for RRLaundry.
All entities in Prayagraj, Civil Lines.
Run: python manage.py seed_demo
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


_DEMO_PW = 'Demo@1234'
_CITY = 'Prayagraj'
_AREA = 'Civil Lines'


class Command(BaseCommand):
    help = 'Seed demo accounts, orders, and RFID history (idempotent).'

    def handle(self, *args, **options):
        self._create_accounts()
        self._create_profiles()
        self._create_partner_selection()
        self._create_orders()
        self.stdout.write(self.style.SUCCESS(
            '\nDemo data seeded.\n'
            f'  hospital@demo.rrlaundry.in  /  {_DEMO_PW}  (Hospital Head)\n'
            f'  laundry@demo.rrlaundry.in   /  {_DEMO_PW}  (Laundry Admin)\n'
            f'  delivery@demo.rrlaundry.in  /  {_DEMO_PW}  (Delivery Partner)\n'
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1 — Accounts
    # ─────────────────────────────────────────────────────────────────────────

    def _create_accounts(self):
        from accounts.models import User, Role

        specs = [
            ('hospital@demo.rrlaundry.in',  'Dr. Ramesh Verma',  Role.HOSPITAL_HEAD),
            ('laundry@demo.rrlaundry.in',   'Suresh Dubey',      Role.LAUNDRY_ADMIN),
            ('delivery@demo.rrlaundry.in',  'Anil Kumar',        Role.DELIVERY_PARTNER),
            ('staff@demo.rrlaundry.in',     'Meena Yadav',       Role.HOSPITAL_STAFF),
            ('worker@demo.rrlaundry.in',    'Ravi Patel',        Role.LAUNDRY_WORKER),
        ]

        self._users = {}
        for email, name, role in specs:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'full_name': name,
                    'role': role,
                    'is_onboarded': True,
                    'is_active': True,
                },
            )
            if created:
                user.set_password(_DEMO_PW)
                user.save(update_fields=['password'])
                self.stdout.write(f'  Created user {email}')
            else:
                self.stdout.write(f'  Exists  user {email}')
            self._users[role] = user

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2 — Profiles
    # ─────────────────────────────────────────────────────────────────────────

    def _create_profiles(self):
        from accounts.models import (
            HospitalProfile, HospitalDepartment, HospitalStaffProfile,
            LaundryProfile, LaundryWorkerProfile, DeliveryProfile, Role,
        )

        # Hospital
        self._hospital, _ = HospitalProfile.objects.get_or_create(
            user=self._users[Role.HOSPITAL_HEAD],
            defaults={
                'hospital_name': 'Civil Lines Medical Centre',
                'hospital_address': '14 Civil Lines, Prayagraj',
                'city': _CITY,
                'area': _AREA,
                'phone_number': '9876543210',
            },
        )

        # Departments
        dept_names = ['ICU', 'Surgery', 'General Ward']
        self._depts = {}
        for name in dept_names:
            dept, _ = HospitalDepartment.objects.get_or_create(
                hospital=self._hospital,
                department_name=name,
            )
            self._depts[name] = dept

        # Hospital Staff
        HospitalStaffProfile.objects.get_or_create(
            user=self._users[Role.HOSPITAL_STAFF],
            defaults={
                'hospital': self._hospital,
                'department': self._depts['ICU'],
                'phone_number': '9876500001',
            },
        )

        # Laundry
        self._laundry, _ = LaundryProfile.objects.get_or_create(
            user=self._users[Role.LAUNDRY_ADMIN],
            defaults={
                'business_name': 'Civil Lines Fresh Laundry',
                'address': '22 Civil Lines Market, Prayagraj',
                'city': _CITY,
                'area': _AREA,
                'phone_number': '9876543211',
                'price_per_item': '5.00',
                'is_available': True,
            },
        )

        # Worker
        LaundryWorkerProfile.objects.get_or_create(
            user=self._users[Role.LAUNDRY_WORKER],
            defaults={
                'laundry': self._laundry,
                'phone_number': '9876500002',
            },
        )

        # Delivery
        self._delivery, _ = DeliveryProfile.objects.get_or_create(
            user=self._users[Role.DELIVERY_PARTNER],
            defaults={
                'city': _CITY,
                'area': _AREA,
                'phone_number': '9876543212',
                'vehicle_type': 'BIKE',
                'is_available': True,
            },
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Step 3 — Partner Selection
    # ─────────────────────────────────────────────────────────────────────────

    def _create_partner_selection(self):
        from hospital.models import HospitalPartnerSelection

        HospitalPartnerSelection.objects.get_or_create(
            hospital=self._hospital,
            laundry_partner=self._laundry,
            delivery_partner=self._delivery,
            defaults={'is_active': True},
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Step 4 — Orders
    # ─────────────────────────────────────────────────────────────────────────

    def _create_orders(self):
        from hospital.models import (
            ItemStatus, ItemType, LaundryOrder, OrderItem, OrderStatus,
        )
        from rfid.models import ReconciliationLog, RFIDScanEvent, ScanPoint
        from laundry.models import MissingItemAlert

        now = timezone.now()
        head = self._users['HOSPITAL_HEAD']

        # ── Order 1: COMPLETED (full RFID chain) ────────────────────────────
        o1, o1_created = LaundryOrder.objects.get_or_create(
            hospital=self._hospital,
            laundry_partner=self._laundry,
            delivery_partner=self._delivery,
            department=self._depts['ICU'],
            status=OrderStatus.COMPLETED,
            defaults={'created_by': head},
        )

        if o1_created:
            tags_o1 = ['DEMO-ICU-01', 'DEMO-ICU-02', 'DEMO-ICU-03']
            items_o1 = OrderItem.objects.bulk_create([
                OrderItem(
                    order=o1, tag_number=t, item_type=ItemType.BEDSHEET,
                    current_status=ItemStatus.COMPLETED,
                    department=self._depts['ICU'],
                    last_scanned_at=now,
                )
                for t in tags_o1
            ])
            # Reconciliation log — all scans matched
            for from_sp, to_sp in [
                (ScanPoint.S1_PICKUP, ScanPoint.S2_RECEIVED),
                (ScanPoint.S2_RECEIVED, ScanPoint.S3_DISPATCH),
                (ScanPoint.S3_DISPATCH, ScanPoint.S4_DELIVERY),
            ]:
                ReconciliationLog.objects.create(
                    order=o1, scan_point_from=from_sp, scan_point_to=to_sp,
                    expected_count=3, received_count=3,
                    missing_tags=[], is_matched=True,
                )
            # Generate invoice
            try:
                from billing.utils import create_invoice_for_order
                create_invoice_for_order(o1)
            except Exception:
                pass
            self.stdout.write(f'  Created Order 1 (COMPLETED): {o1.short_id}')

        # ── Order 2: AT_LAUNDRY ──────────────────────────────────────────────
        o2, o2_created = LaundryOrder.objects.get_or_create(
            hospital=self._hospital,
            laundry_partner=self._laundry,
            delivery_partner=self._delivery,
            department=self._depts['Surgery'],
            status=OrderStatus.AT_LAUNDRY,
            defaults={'created_by': head},
        )

        if o2_created:
            tags_o2 = ['DEMO-SRG-01', 'DEMO-SRG-02']
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=o2, tag_number=t, item_type=ItemType.OT_DRAPE,
                    current_status=ItemStatus.AT_LAUNDRY,
                    department=self._depts['Surgery'],
                    last_scanned_at=now,
                )
                for t in tags_o2
            ])
            ReconciliationLog.objects.create(
                order=o2,
                scan_point_from=ScanPoint.S1_PICKUP,
                scan_point_to=ScanPoint.S2_RECEIVED,
                expected_count=2, received_count=2,
                missing_tags=[], is_matched=True,
            )
            self.stdout.write(f'  Created Order 2 (AT_LAUNDRY): {o2.short_id}')

        # ── Order 3: CREATED — one stale item ───────────────────────────────
        o3, o3_created = LaundryOrder.objects.get_or_create(
            hospital=self._hospital,
            laundry_partner=self._laundry,
            delivery_partner=self._delivery,
            department=self._depts['General Ward'],
            status=OrderStatus.CREATED,
            defaults={'created_by': head},
        )

        if o3_created:
            stale_item = OrderItem.objects.create(
                order=o3, tag_number='DEMO-GW-01',
                item_type=ItemType.PATIENT_GOWN,
                current_status=ItemStatus.AT_LAUNDRY,
                department=self._depts['General Ward'],
                last_scanned_at=now - timezone.timedelta(hours=2),
            )
            MissingItemAlert.objects.get_or_create(
                order_item=stale_item,
                defaults={
                    'last_updated_at': stale_item.last_scanned_at,
                    'last_stage': ItemStatus.AT_LAUNDRY,
                    'is_resolved': False,
                },
            )
            self.stdout.write(f'  Created Order 3 (CREATED + stale alert): {o3.short_id}')
