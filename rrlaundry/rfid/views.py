from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from hospital.models import OrderItem
from .models import RFIDScanEvent, ScanPoint


_SCAN_POINT_META = {
    ScanPoint.S1_PICKUP:   ('S1 — Pickup',            'Hospital',      'pickup'),
    ScanPoint.S2_RECEIVED: ('S2 — Received at Plant',  'Laundry Plant', 'received'),
    ScanPoint.S3_DISPATCH: ('S3 — Dispatched',         'Laundry Plant', 'dispatch'),
    ScanPoint.S4_DELIVERY: ('S4 — Delivered',          'Hospital',      'delivery'),
}


class TagHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'rfid/tag_history.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tag_number = self.kwargs['tag_number'].strip().upper()

        events = (
            RFIDScanEvent.objects
            .filter(tag_number=tag_number)
            .select_related('scanned_by', 'order__hospital', 'order__created_by')
            .order_by('scanned_at')
        )

        timeline = []

        try:
            item = (
                OrderItem.objects
                .select_related(
                    'order__hospital', 'order__created_by',
                    'order__laundry_partner', 'order__delivery_partner',
                )
                .get(tag_number=tag_number)
            )
            order = item.order
            creator = order.created_by
            timeline.append({
                'label':     'Order Created',
                'timestamp': order.created_at,
                'actor':     creator.full_name or creator.email if creator else '—',
                'location':  order.hospital.hospital_name,
                'icon':      'create',
                'status':    'ok',
            })
        except OrderItem.DoesNotExist:
            item = None
            order = None

        for ev in events:
            label, default_loc, icon = _SCAN_POINT_META.get(
                ev.scan_point, (ev.scan_point, '', 'scan'),
            )
            actor = '—'
            if ev.scanned_by:
                actor = ev.scanned_by.full_name or ev.scanned_by.email
            timeline.append({
                'label':     label,
                'timestamp': ev.scanned_at,
                'actor':     actor,
                'location':  ev.location_note or default_loc,
                'icon':      icon,
                'status':    'ok',
            })

        ctx.update({
            'tag_number': tag_number,
            'item':       item,
            'order':      order,
            'timeline':   timeline,
        })
        return ctx
