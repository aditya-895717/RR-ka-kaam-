from django.urls import path

from .views import (
    AlertsView, DeactivateWorkerView, LaundryDashboardView, LaundryOrderListView,
    PricingView, ProcessingFloorView, ReactivateWorkerView, ScanDispatchView,
    ScanItemsView, ScanReceiveView, UpdateItemStageView, WorkerManagementView,
)

urlpatterns = [
    path('dashboard/',                           LaundryDashboardView.as_view(),  name='laundry_dashboard'),
    path('floor/',                               ProcessingFloorView.as_view(),   name='laundry_floor'),
    path('floor/update/',                        UpdateItemStageView.as_view(),   name='laundry_update_stage'),
    path('scan/',                                ScanItemsView.as_view(),         name='laundry_scan_items'),
    path('scan/receive/<uuid:order_id>/',        ScanReceiveView.as_view(),       name='laundry_scan_receive'),
    path('scan/dispatch/<uuid:order_id>/',       ScanDispatchView.as_view(),      name='laundry_scan_dispatch'),
    path('orders/',                              LaundryOrderListView.as_view(),  name='laundry_order_list'),
    path('pricing/',                             PricingView.as_view(),           name='laundry_pricing'),
    path('workers/',                             WorkerManagementView.as_view(),  name='laundry_workers'),
    path('workers/<uuid:user_id>/deactivate/',   DeactivateWorkerView.as_view(),  name='laundry_deactivate_worker'),
    path('workers/<uuid:user_id>/reactivate/',   ReactivateWorkerView.as_view(),  name='laundry_reactivate_worker'),
    path('alerts/',                              AlertsView.as_view(),            name='laundry_alerts'),
]
