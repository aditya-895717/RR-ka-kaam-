import logging
import secrets

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from django.urls import reverse

from accounts.forms import AdminCreateStaffForm
from accounts.models import (
    DeliveryProfile, HospitalDepartment, HospitalProfile,
    HospitalStaffProfile, LaundryProfile, Role, User,
)
from .forms import DepartmentForm, NewOrderForm, OrderFilterForm
from .models import (
    HospitalPartnerSelection, ItemStatus, ItemType,
    LaundryOrder, OrderItem, OrderStatus,
)

logger = logging.getLogger(__name__)

_SESSION_LAUNDRY  = 'partner_sel_laundry'
_SESSION_DELIVERY = 'partner_sel_delivery'


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_hospital_profile(user):
    try:
        return user.hospital_profile
    except Exception:
        pass
    try:
        return user.hospital_staff_profile.hospital
    except Exception:
        return None


def _notify_delivery_partner(order):
    if not order.delivery_partner:
        return
    try:
        from notifications.brevo import send_job_assigned_email
        dp = order.delivery_partner
        send_job_assigned_email(
            dp.user.email,
            dp.user.full_name or dp.user.email,
            order,
            'Pickup',
        )
    except Exception as exc:
        logger.warning('Could not notify delivery partner for order %s: %s', order.order_id, exc)


# ─── Mixin ───────────────────────────────────────────────────────────────────

class HospitalViewMixin(View):
    hospital_head_only = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.conf import settings
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role not in (Role.HOSPITAL_HEAD, Role.HOSPITAL_STAFF):
            raise PermissionDenied
        if self.hospital_head_only and request.user.role != Role.HOSPITAL_HEAD:
            raise PermissionDenied
        self.profile = _get_hospital_profile(request.user)
        if not self.profile:
            return redirect('account_onboarding')
        return super().dispatch(request, *args, **kwargs)

    def ctx(self, **extra):
        return {'profile': self.profile, **extra}


# ─── Views ───────────────────────────────────────────────────────────────────

class HospitalDashboardView(HospitalViewMixin):
    def get(self, request):
        from django.utils import timezone
        today = timezone.now().date()

        active_orders  = LaundryOrder.objects.filter(
            hospital=self.profile,
        ).exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.FLAGGED]).count()

        pending_confirm = LaundryOrder.objects.filter(
            hospital=self.profile, status=OrderStatus.DELIVERED,
        ).count()

        items_today = OrderItem.objects.filter(
            order__hospital=self.profile,
            added_at__date=today,
        ).count()

        recent_orders = (
            LaundryOrder.objects
            .filter(hospital=self.profile)
            .select_related('department', 'laundry_partner')
            .prefetch_related('items')[:10]
        )

        selection = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, is_active=True,
        ).select_related('laundry_partner', 'delivery_partner').first()

        return render(request, 'hospital/dashboard.html', self.ctx(
            active_orders=active_orders,
            pending_confirm=pending_confirm,
            items_today=items_today,
            dept_count=self.profile.departments.count(),
            recent_orders=recent_orders,
            selection=selection,
        ))


class PartnerSelectionView(HospitalViewMixin):
    hospital_head_only = True

    def get(self, request):
        from core.discovery import get_available_delivery_partners, get_available_laundry_partners
        step = request.GET.get('step', '1')
        current = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, is_active=True,
        ).select_related('laundry_partner', 'delivery_partner__user').first()

        if step == '3':
            laundry_id  = request.session.get(_SESSION_LAUNDRY)
            delivery_id = request.session.get(_SESSION_DELIVERY)
            if not laundry_id or not delivery_id:
                return redirect('hospital_partners')
            selected_laundry  = LaundryProfile.objects.filter(pk=laundry_id).first()
            selected_delivery = DeliveryProfile.objects.select_related('user').filter(pk=delivery_id).first()
            if not selected_laundry or not selected_delivery:
                return redirect('hospital_partners')
            return render(request, 'hospital/partner_selection.html', self.ctx(
                step=3,
                selected_laundry=selected_laundry,
                selected_delivery=selected_delivery,
                current=current,
            ))

        if step == '2':
            laundry_id = request.session.get(_SESSION_LAUNDRY)
            if not laundry_id:
                return redirect('hospital_partners')
            selected_laundry  = LaundryProfile.objects.filter(pk=laundry_id).first()
            delivery_partners = get_available_delivery_partners(self.profile)
            return render(request, 'hospital/partner_selection.html', self.ctx(
                step=2,
                selected_laundry=selected_laundry,
                delivery_partners=delivery_partners,
                current=current,
            ))

        laundry_partners = get_available_laundry_partners(self.profile)
        return render(request, 'hospital/partner_selection.html', self.ctx(
            step=1,
            laundry_partners=laundry_partners,
            current=current,
        ))

    def post(self, request):
        step = request.POST.get('step', '1')
        base_url = reverse('hospital_partners')

        if step == '1':
            laundry_id = request.POST.get('laundry_id')
            if not laundry_id or not LaundryProfile.objects.filter(pk=laundry_id).exists():
                messages.error(request, 'Please select a valid laundry partner.')
                return redirect('hospital_partners')
            request.session[_SESSION_LAUNDRY] = int(laundry_id)
            return redirect(f'{base_url}?step=2')

        if step == '2':
            delivery_id = request.POST.get('delivery_id')
            if not delivery_id or not DeliveryProfile.objects.filter(pk=delivery_id).exists():
                messages.error(request, 'Please select a valid delivery partner.')
                return redirect(f'{base_url}?step=2')
            request.session[_SESSION_DELIVERY] = int(delivery_id)
            return redirect(f'{base_url}?step=3')

        # step 3 — final confirmation
        laundry_id  = request.session.get(_SESSION_LAUNDRY)
        delivery_id = request.session.get(_SESSION_DELIVERY)
        if not laundry_id or not delivery_id:
            messages.error(request, 'Partner selection incomplete. Please start over.')
            return redirect('hospital_partners')

        laundry  = get_object_or_404(LaundryProfile, pk=laundry_id)
        delivery = get_object_or_404(DeliveryProfile, pk=delivery_id)

        with transaction.atomic():
            HospitalPartnerSelection.objects.filter(
                hospital=self.profile,
            ).update(is_active=False)
            HospitalPartnerSelection.objects.create(
                hospital=self.profile,
                laundry_partner=laundry,
                delivery_partner=delivery,
                is_active=True,
            )

        request.session.pop(_SESSION_LAUNDRY, None)
        request.session.pop(_SESSION_DELIVERY, None)
        messages.success(request, 'Partners selected successfully.')
        return redirect('hospital_dashboard')


class ChangePartnerView(HospitalViewMixin):
    hospital_head_only = True

    def get(self, request):
        active_count = LaundryOrder.objects.filter(
            hospital=self.profile,
        ).exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.FLAGGED]).count()

        if active_count:
            return render(request, 'hospital/partner_selection.html', self.ctx(
                step='blocked',
                active_order_count=active_count,
            ))

        request.session.pop(_SESSION_LAUNDRY, None)
        request.session.pop(_SESSION_DELIVERY, None)
        return redirect('hospital_partners')


class LaundryPartnerProfileView(HospitalViewMixin):
    def get(self, request, partner_id):
        from django.db.models import Count
        partner = get_object_or_404(
            LaundryProfile.objects.annotate(total_orders=Count('orders')),
            pk=partner_id,
            city__iexact=self.profile.city,
        )
        is_current = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, laundry_partner=partner, is_active=True,
        ).exists()
        return render(request, 'hospital/laundry_partner_profile.html', self.ctx(
            partner=partner,
            is_current=is_current,
        ))


class DeliveryPartnerProfileView(HospitalViewMixin):
    def get(self, request, partner_id):
        partner = get_object_or_404(
            DeliveryProfile.objects.select_related('user'),
            pk=partner_id,
            city__iexact=self.profile.city,
        )
        is_current = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, delivery_partner=partner, is_active=True,
        ).exists()
        return render(request, 'hospital/delivery_partner_profile.html', self.ctx(
            partner=partner,
            is_current=is_current,
        ))


class DepartmentManagementView(HospitalViewMixin):
    hospital_head_only = True

    def get(self, request):
        departments = HospitalDepartment.objects.filter(hospital=self.profile)
        form = DepartmentForm()
        return render(request, 'hospital/departments.html', self.ctx(
            departments=departments, form=form,
        ))

    def post(self, request):
        action = request.POST.get('action', 'add')

        if action == 'add':
            form = DepartmentForm(request.POST)
            if form.is_valid():
                HospitalDepartment.objects.create(
                    hospital=self.profile,
                    department_name=form.cleaned_data['department_name'],
                )
                messages.success(request, 'Department added.')
                return redirect('hospital_departments')
            departments = HospitalDepartment.objects.filter(hospital=self.profile)
            return render(request, 'hospital/departments.html', self.ctx(
                departments=departments, form=form,
            ))

        if action == 'edit':
            dept_id = request.POST.get('dept_id')
            new_name = request.POST.get('department_name', '').strip()
            dept = get_object_or_404(HospitalDepartment, pk=dept_id, hospital=self.profile)
            if new_name:
                dept.department_name = new_name
                dept.save(update_fields=['department_name'])
                messages.success(request, 'Department updated.')
            return redirect('hospital_departments')

        if action == 'delete':
            dept_id = request.POST.get('dept_id')
            dept = get_object_or_404(HospitalDepartment, pk=dept_id, hospital=self.profile)
            dept.delete()
            messages.success(request, 'Department deleted.')
            return redirect('hospital_departments')

        return redirect('hospital_departments')


class NewOrderView(HospitalViewMixin):
    def get(self, request):
        selection = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, is_active=True,
        ).select_related('laundry_partner', 'delivery_partner').first()

        if not selection:
            messages.warning(request, 'Please select your laundry and delivery partners first.')
            return redirect('hospital_partners')

        form = NewOrderForm(hospital=self.profile)
        return render(request, 'hospital/new_order.html', self.ctx(
            form=form,
            selection=selection,
            item_types=ItemType.choices,
        ))

    def post(self, request):
        selection = HospitalPartnerSelection.objects.filter(
            hospital=self.profile, is_active=True,
        ).select_related('laundry_partner', 'delivery_partner').first()

        if not selection:
            return redirect('hospital_partners')

        form = NewOrderForm(hospital=self.profile, data=request.POST)
        tag_numbers = [t.strip().upper() for t in request.POST.getlist('tag_numbers') if t.strip()]
        item_types  = request.POST.getlist('item_types')

        errors = []
        if not form.is_valid():
            errors.append('Please select a department.')
        if not tag_numbers:
            errors.append('Add at least one item to the order.')
        if len(tag_numbers) != len(item_types):
            errors.append('Item data mismatch — please re-add items and try again.')
        if len(tag_numbers) != len(set(tag_numbers)):
            errors.append('Duplicate tag numbers detected in this submission.')

        if not errors:
            existing = list(
                OrderItem.objects.filter(tag_number__in=tag_numbers)
                .values_list('tag_number', flat=True)
            )
            if existing:
                errors.append(f"Tag numbers already in system: {', '.join(existing)}")

        if errors:
            return render(request, 'hospital/new_order.html', self.ctx(
                form=form,
                selection=selection,
                item_types=ItemType.choices,
                errors=errors,
                prev_items=[{'tag': t, 'type': tp} for t, tp in zip(tag_numbers, item_types)],
            ))

        dept = form.cleaned_data['department']

        with transaction.atomic():
            order = LaundryOrder.objects.create(
                hospital=self.profile,
                laundry_partner=selection.laundry_partner,
                delivery_partner=selection.delivery_partner,
                department=dept,
                status=OrderStatus.CREATED,
                created_by=request.user,
            )
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    tag_number=tag,
                    item_type=itype,
                    current_status=ItemStatus.WITH_HOSPITAL,
                    department=dept,
                )
                for tag, itype in zip(tag_numbers, item_types)
            ])

        from delivery.utils import create_pickup_job
        create_pickup_job(order)
        _notify_delivery_partner(order)
        messages.success(request, f'Order #{order.short_id} created with {len(tag_numbers)} items.')
        return redirect('hospital_order_detail', order_id=order.order_id)


class OrderListView(HospitalViewMixin):
    def get(self, request):
        form = OrderFilterForm(request.GET or None)
        qs = (
            LaundryOrder.objects
            .filter(hospital=self.profile)
            .select_related('department', 'laundry_partner', 'delivery_partner')
            .prefetch_related('items')
        )

        # Hospital Staff: restrict to their department
        if request.user.role == Role.HOSPITAL_STAFF:
            try:
                staff_dept = request.user.hospital_staff_profile.department
                if staff_dept:
                    qs = qs.filter(department=staff_dept)
            except Exception:
                pass

        if form.is_valid():
            if form.cleaned_data.get('status'):
                qs = qs.filter(status=form.cleaned_data['status'])
            if form.cleaned_data.get('date_from'):
                qs = qs.filter(created_at__date__gte=form.cleaned_data['date_from'])
            if form.cleaned_data.get('date_to'):
                qs = qs.filter(created_at__date__lte=form.cleaned_data['date_to'])
            if form.cleaned_data.get('search'):
                qs = qs.filter(
                    order_id__icontains=form.cleaned_data['search'].replace('-', '').lower()
                )

        paginator = Paginator(qs, 20)
        page = paginator.get_page(request.GET.get('page', 1))

        # Preserve active filters across pagination links. 'page' is stripped so
        # the template can append its own without duplicating the parameter.
        params = request.GET.copy()
        params.pop('page', None)

        return render(request, 'hospital/order_list.html', self.ctx(
            page_obj=page,
            query_string=params.urlencode(),
            filter_form=form,
            total=paginator.count,
        ))


class OrderDetailView(HospitalViewMixin):
    def get(self, request, order_id):
        order = get_object_or_404(
            LaundryOrder.objects
            .select_related('department', 'laundry_partner', 'delivery_partner',
                            'delivery_partner__user', 'created_by')
            .prefetch_related('items'),
            order_id=order_id,
            hospital=self.profile,
        )
        return render(request, 'hospital/order_detail.html', self.ctx(
            order=order,
            items=order.items.all(),
        ))


class ItemTrackingView(HospitalViewMixin):
    def get(self, request):
        tag = request.GET.get('tag', '').strip().upper()
        item = None
        if tag:
            item = (
                OrderItem.objects
                .select_related(
                    'order', 'order__hospital',
                    'order__delivery_partner', 'order__delivery_partner__user',
                    'department',
                )
                .filter(order__hospital=self.profile, tag_number=tag)
                .first()
            )
        return render(request, 'hospital/item_tracking.html', self.ctx(
            tag_query=tag, item=item,
        ))


class DeliveryConfirmationView(HospitalViewMixin):
    def post(self, request, order_id):
        order = get_object_or_404(
            LaundryOrder, order_id=order_id, hospital=self.profile,
        )
        # Receipt acknowledgement only — this is NOT the invoice trigger.
        # Billing fires on the system-verified S4 scan in rfid.engine, which is
        # the single source of truth. Accepts DELIVERED (partial delivery) and
        # COMPLETED (clean S4, already invoiced) so a clean delivery — the
        # normal case — is still acknowledgeable.
        if order.status not in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            messages.error(request, 'Order must be delivered before you can confirm receipt.')
            return redirect('hospital_order_detail', order_id=order_id)

        with transaction.atomic():
            order.status = OrderStatus.COMPLETED
            order.save(update_fields=['status', 'updated_at'])
            order.items.update(current_status=ItemStatus.COMPLETED)

        messages.success(request, f'Order #{order.short_id} confirmed and marked complete.')
        return redirect('hospital_order_detail', order_id=order_id)


# ─── Staff management ─────────────────────────────────────────────────────────

class ManageStaffView(HospitalViewMixin):
    hospital_head_only = True

    def _staff_qs(self):
        return (
            HospitalStaffProfile.objects
            .filter(hospital=self.profile)
            .select_related('user', 'department')
            .order_by('user__full_name')
        )

    def get(self, request):
        return render(request, 'hospital/staff.html', self.ctx(
            staff=self._staff_qs(),
            form=AdminCreateStaffForm(hospital=self.profile),
        ))

    def post(self, request):
        form = AdminCreateStaffForm(request.POST, hospital=self.profile)
        if not form.is_valid():
            return render(request, 'hospital/staff.html', self.ctx(
                staff=self._staff_qs(), form=form,
            ))
        cd = form.cleaned_data
        password = secrets.token_urlsafe(10)
        with transaction.atomic():
            user = User.objects.create_user(
                email=cd['email'],
                password=password,
                full_name=cd['full_name'],
                phone_number=cd.get('phone_number', ''),
                role=Role.HOSPITAL_STAFF,
                is_onboarded=True,
            )
            HospitalStaffProfile.objects.create(
                user=user,
                hospital=self.profile,
                department=cd.get('department'),
                phone_number=cd.get('phone_number', ''),
            )
        messages.success(
            request,
            f'Account created for {cd["full_name"] or cd["email"]}. '
            f'Temporary password: {password} — share securely (shown once).',
        )
        return redirect('hospital_manage_staff')


class DeactivateStaffView(HospitalViewMixin):
    hospital_head_only = True

    def post(self, request, user_id):
        sp = get_object_or_404(HospitalStaffProfile, user_id=user_id, hospital=self.profile)
        sp.user.is_active = False
        sp.user.save(update_fields=['is_active'])
        messages.success(request, f'{sp.user.full_name or sp.user.email} has been deactivated.')
        return redirect('hospital_manage_staff')


class ReactivateStaffView(HospitalViewMixin):
    hospital_head_only = True

    def post(self, request, user_id):
        sp = get_object_or_404(HospitalStaffProfile, user_id=user_id, hospital=self.profile)
        sp.user.is_active = True
        sp.user.save(update_fields=['is_active'])
        messages.success(request, f'{sp.user.full_name or sp.user.email} has been reactivated.')
        return redirect('hospital_manage_staff')
