from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import LaundryProfile, LaundryWorkerProfile, Role, User
from hospital.models import ItemStatus, OrderItem

from .models import (
    FloorStage, IN_PROGRESS_STAGES, STAGE_TO_ITEM_STATUS,
    ItemStageLog, MissingItemAlert, WorkerItemAssignment,
)
from .serializers import (
    AlertSerializer, FloorItemSerializer, PricingUpdateSerializer,
    StageUpdateSerializer, WorkerAssignSerializer,
)

_FLOOR_STATUSES = [ItemStatus.AT_LAUNDRY, ItemStatus.WASHED]


def _get_laundry_profile(user):
    try:
        return user.laundry_profile
    except LaundryProfile.DoesNotExist:
        pass
    try:
        return user.laundry_worker_profile.laundry
    except (LaundryWorkerProfile.DoesNotExist, AttributeError):
        pass
    return None


class _LaundryAPIBase(APIView):
    permission_classes = [IsAuthenticated]
    admin_only = False

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        role = request.user.role
        if role not in (Role.LAUNDRY_ADMIN, Role.LAUNDRY_WORKER):
            self.permission_denied(request)
        if self.admin_only and role != Role.LAUNDRY_ADMIN:
            self.permission_denied(request)
        self.profile = _get_laundry_profile(request.user)
        if not self.profile:
            self.permission_denied(request)


class FloorListAPI(_LaundryAPIBase):
    def get(self, request):
        from django.db.models import OuterRef, Subquery
        latest_log_sub = ItemStageLog.objects.filter(
            order_item=OuterRef('pk'),
        ).order_by('-updated_at').values('stage')[:1]

        items = (
            OrderItem.objects
            .filter(
                order__laundry_partner=self.profile,
                current_status__in=_FLOOR_STATUSES,
            )
            .prefetch_related('stage_logs', 'worker_assignments__worker', 'alerts')
            .select_related('order__hospital', 'department')
        )
        ser = FloorItemSerializer(items, many=True)
        return Response(ser.data)


class UpdateItemStageAPI(_LaundryAPIBase):
    def post(self, request, tag_number):
        item = get_object_or_404(
            OrderItem,
            tag_number=tag_number,
            order__laundry_partner=self.profile,
        )
        ser = StageUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        new_stage = ser.validated_data['new_stage']
        worker_id = ser.validated_data.get('worker_id')
        notes     = ser.validated_data.get('notes', '')

        # Washing gate: require first worker
        if new_stage == FloorStage.WASHING:
            has_first = WorkerItemAssignment.objects.filter(
                order_item=item, is_first_worker=True,
            ).exists()
            if not has_first:
                if not worker_id:
                    return Response(
                        {'detail': 'worker_id is required when moving to WASHING for the first time.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    worker = User.objects.get(pk=worker_id, laundry_worker_profile__laundry=self.profile)
                except User.DoesNotExist:
                    return Response({'detail': 'Worker not found.'}, status=status.HTTP_400_BAD_REQUEST)
                WorkerItemAssignment.objects.create(
                    order_item=item, worker=worker, is_first_worker=True,
                )

        ItemStageLog.objects.create(
            order_item=item, stage=new_stage, updated_by=request.user, notes=notes,
        )

        new_item_status = STAGE_TO_ITEM_STATUS.get(new_stage)
        if new_item_status:
            item.current_status = new_item_status
            item.save(update_fields=['current_status'])

        return Response({'tag_number': tag_number, 'new_stage': new_stage, 'status': 'updated'})


class AssignWorkerAPI(_LaundryAPIBase):
    def post(self, request, tag_number):
        item = get_object_or_404(
            OrderItem,
            tag_number=tag_number,
            order__laundry_partner=self.profile,
        )
        ser = WorkerAssignSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        worker_id = ser.validated_data['worker_id']
        try:
            worker = User.objects.get(pk=worker_id, laundry_worker_profile__laundry=self.profile)
        except User.DoesNotExist:
            return Response({'detail': 'Worker not found.'}, status=status.HTTP_400_BAD_REQUEST)

        # If no first_worker set yet, make this one
        is_first = not WorkerItemAssignment.objects.filter(
            order_item=item, is_first_worker=True,
        ).exists()

        WorkerItemAssignment.objects.create(
            order_item=item, worker=worker, is_first_worker=is_first,
        )
        return Response({
            'tag_number': tag_number,
            'worker': str(worker_id),
            'is_first_worker': is_first,
        })


class AlertListAPI(_LaundryAPIBase):
    def get(self, request):
        my_item_ids = OrderItem.objects.filter(
            order__laundry_partner=self.profile,
        ).values_list('id', flat=True)

        alerts = (
            MissingItemAlert.objects
            .filter(order_item_id__in=my_item_ids, is_resolved=False)
            .select_related('order_item__order__hospital', 'assigned_worker')
        )
        ser = AlertSerializer(alerts, many=True)
        return Response(ser.data)


class ResolveAlertAPI(_LaundryAPIBase):
    def post(self, request, pk):
        alert = get_object_or_404(
            MissingItemAlert,
            pk=pk,
            order_item__order__laundry_partner=self.profile,
        )
        if alert.is_resolved:
            return Response({'detail': 'Alert already resolved.'}, status=status.HTTP_400_BAD_REQUEST)
        alert.resolve()
        ser = AlertSerializer(alert)
        return Response(ser.data)


class UpdatePricingAPI(_LaundryAPIBase):
    admin_only = True

    def post(self, request):
        ser = PricingUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        self.profile.price_per_item = ser.validated_data['price_per_item']
        self.profile.save(update_fields=['price_per_item'])
        return Response({
            'price_per_item': str(self.profile.price_per_item),
            'status': 'updated',
        })
