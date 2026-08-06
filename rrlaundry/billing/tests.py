from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import HospitalDepartment, Role
from billing.engine import generate_invoice
from billing.models import Invoice, InvoiceLineItem
from core.test_factories import (
    make_hospital_profile, make_laundry_profile, make_order, make_user,
)
from hospital.models import ItemStatus, ItemType, LaundryOrder, OrderItem, OrderStatus


def _make_delivered_item(order, tag, department=None):
    return OrderItem.objects.create(
        order=order,
        tag_number=tag,
        item_type=ItemType.BEDSHEET,
        current_status=ItemStatus.DELIVERED,
        department=department,
    )


class InvoiceGenerationTests(TestCase):
    def setUp(self):
        hospital_user     = make_user('hosp@billing.com',    Role.HOSPITAL_HEAD)
        laundry_user      = make_user('laundry@billing.com', Role.LAUNDRY_ADMIN)
        self.hospital     = make_hospital_profile(hospital_user)
        self.laundry      = make_laundry_profile(laundry_user, price_per_item=Decimal('50.00'))
        self.dept         = HospitalDepartment.objects.create(
            hospital=self.hospital,
            department_name='ICU',
        )
        self.order = make_order(
            self.hospital,
            laundry=self.laundry,
            status=OrderStatus.DELIVERED,
        )

    def test_total_items_and_amount_correct(self):
        for i in range(3):
            _make_delivered_item(self.order, f'INV-{i:04d}')
        invoice = generate_invoice(self.order.order_id)
        self.assertEqual(invoice.total_items, 3)
        self.assertEqual(invoice.total_amount, Decimal('150.00'))
        self.assertEqual(invoice.price_per_item, Decimal('50.00'))

    def test_invoice_number_format(self):
        _make_delivered_item(self.order, 'INV-FMT-0001')
        invoice = generate_invoice(self.order.order_id)
        today = timezone.now().strftime('%Y%m%d')
        prefix = f'INV-{today}-'
        self.assertTrue(invoice.invoice_number.startswith(prefix))
        seq_part = invoice.invoice_number[len(prefix):]
        self.assertEqual(len(seq_part), 4)
        self.assertTrue(seq_part.isdigit())

    def test_invoice_numbers_are_sequential(self):
        _make_delivered_item(self.order, 'INV-SEQ-0001')
        inv1 = generate_invoice(self.order.order_id)

        order2 = make_order(
            self.hospital,
            laundry=self.laundry,
            status=OrderStatus.DELIVERED,
        )
        _make_delivered_item(order2, 'INV-SEQ-0002')
        inv2 = generate_invoice(order2.order_id)

        seq1 = int(inv1.invoice_number.split('-')[-1])
        seq2 = int(inv2.invoice_number.split('-')[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_line_items_grouped_by_department(self):
        dept2 = HospitalDepartment.objects.create(
            hospital=self.hospital, department_name='Surgery'
        )
        for i in range(2):
            _make_delivered_item(self.order, f'DEPT1-{i:04d}', department=self.dept)
        _make_delivered_item(self.order, 'DEPT2-0001', department=dept2)

        invoice = generate_invoice(self.order.order_id)

        self.assertEqual(invoice.total_items, 3)
        self.assertEqual(invoice.total_amount, Decimal('150.00'))

        line_items = InvoiceLineItem.objects.filter(invoice=invoice)
        self.assertEqual(line_items.count(), 2)

        icu = line_items.get(department=self.dept)
        self.assertEqual(icu.item_count, 2)
        self.assertEqual(icu.line_total, Decimal('100.00'))

        surgery = line_items.get(department=dept2)
        self.assertEqual(surgery.item_count, 1)
        self.assertEqual(surgery.line_total, Decimal('50.00'))

    def test_zero_delivered_items_generates_zero_invoice(self):
        invoice = generate_invoice(self.order.order_id)
        self.assertEqual(invoice.total_items, 0)
        self.assertEqual(invoice.total_amount, Decimal('0.00'))
        self.assertEqual(InvoiceLineItem.objects.filter(invoice=invoice).count(), 0)

    def test_invoice_status_is_pending(self):
        _make_delivered_item(self.order, 'INV-STATUS-0001')
        invoice = generate_invoice(self.order.order_id)
        self.assertEqual(invoice.status, 'PENDING')

    def test_invoice_is_overdue_when_past_due_date(self):
        _make_delivered_item(self.order, 'INV-OVERDUE-0001')
        invoice = generate_invoice(self.order.order_id)
        # Artificially push due_date into the past
        from datetime import timedelta
        invoice.due_date = timezone.now() - timedelta(days=1)
        invoice.save()
        self.assertTrue(invoice.is_overdue())

    def test_duplicate_invoice_raises(self):
        _make_delivered_item(self.order, 'INV-DUP-0001')
        generate_invoice(self.order.order_id)
        # Second call → OneToOne violation on order
        with self.assertRaises(Exception):
            generate_invoice(self.order.order_id)
