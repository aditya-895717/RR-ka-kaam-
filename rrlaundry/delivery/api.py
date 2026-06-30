import json

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DeliveryProfile, Role
from hospital.models import ItemStatus

from .models import DeliveryJob, JobStatus, JobType
from .serializers import DeliveryJobSerializer, ScanSubmitSerializer
from .utils import (
    create_delivery_job, process_delivery_scan, process_pickup_scan,
    send_delivery_confirmation, send_pickup_confirmation,
)


class _DeliveryAPIBase(APIView):
    def _get_profile(self, request):
        if not request.user.is_authenticated:
            return None, Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        if request.user.role != Role.DELIVERY_PARTNER:
            return None, Response({'detail': 'Delivery partner access required.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            return request.user.delivery_profile, None
        except DeliveryProfile.DoesNotExist:
            return None, Response({'detail': 'Delivery profile not found.'}, status=status.HTTP_404_NOT_FOUND)


class JobListAPI(_DeliveryAPIBase):
    def get(self, request):
        profile, err = self._get_profile(request)
        if err:
            return err

        qs = (
            DeliveryJob.objects
            .filter(delivery_partner=profile)
            .select_related('order__hospital')
            .order_by('-assigned_at')
        )

        job_type   = request.query_params.get('type')
        job_status = request.query_params.get('status')
        if job_type:
            qs = qs.filter(job_type=job_type)
        if job_status:
            qs = qs.filter(status=job_status)

        serializer = DeliveryJobSerializer(qs, many=True)
        return Response(serializer.data)


class JobDetailAPI(_DeliveryAPIBase):
    def get(self, request, job_id):
        profile, err = self._get_profile(request)
        if err:
            return err

        try:
            job = DeliveryJob.objects.select_related('order__hospital').get(
                job_id=job_id, delivery_partner=profile,
            )
        except DeliveryJob.DoesNotExist:
            return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

        items = list(
            job.order.items.values('tag_number', 'item_type', 'current_status')
        )
        data = DeliveryJobSerializer(job).data
        data['items'] = items
        return Response(data)


class StartJobAPI(_DeliveryAPIBase):
    def post(self, request, job_id):
        profile, err = self._get_profile(request)
        if err:
            return err

        try:
            job = DeliveryJob.objects.get(job_id=job_id, delivery_partner=profile)
        except DeliveryJob.DoesNotExist:
            return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

        if job.status != JobStatus.ASSIGNED:
            return Response({'detail': f'Job is already {job.get_status_display()}.'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        job.status = JobStatus.IN_PROGRESS
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])

        return Response({'status': 'IN_PROGRESS', 'started_at': job.started_at})


class CompletePickupAPI(_DeliveryAPIBase):
    def post(self, request, job_id):
        profile, err = self._get_profile(request)
        if err:
            return err

        try:
            job = DeliveryJob.objects.get(
                job_id=job_id, delivery_partner=profile, job_type=JobType.PICKUP,
            )
        except DeliveryJob.DoesNotExist:
            return Response({'detail': 'Pickup job not found.'}, status=status.HTTP_404_NOT_FOUND)

        if job.status == JobStatus.COMPLETED:
            return Response({'detail': 'Job already completed.'}, status=status.HTTP_400_BAD_REQUEST)

        ser = ScanSubmitSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        tag_numbers = [t.strip().upper() for t in ser.validated_data['tag_numbers']]
        scanned_count, unknown = process_pickup_scan(job, tag_numbers)
        send_pickup_confirmation(job.order, scanned_count)

        return Response({
            'scanned': scanned_count,
            'unknown': unknown,
            'order_status': job.order.status,
        })


class CompleteDeliveryAPI(_DeliveryAPIBase):
    def post(self, request, job_id):
        profile, err = self._get_profile(request)
        if err:
            return err

        try:
            job = DeliveryJob.objects.get(
                job_id=job_id, delivery_partner=profile, job_type=JobType.DELIVERY,
            )
        except DeliveryJob.DoesNotExist:
            return Response({'detail': 'Delivery job not found.'}, status=status.HTTP_404_NOT_FOUND)

        if job.status == JobStatus.COMPLETED:
            return Response({'detail': 'Job already completed.'}, status=status.HTTP_400_BAD_REQUEST)

        ser = ScanSubmitSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        tag_numbers = [t.strip().upper() for t in ser.validated_data['tag_numbers']]
        scanned_count, unknown = process_delivery_scan(job, tag_numbers)
        send_delivery_confirmation(job.order, scanned_count)

        return Response({
            'scanned': scanned_count,
            'unknown': unknown,
            'order_status': job.order.status,
        })
