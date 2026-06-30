from django.urls import path

from .views import (
    AlertsView, LaundryDashboardView, LaundryOrderListView,
    PricingView, ProcessingFloorView, UpdateItemStageView, WorkerManagementView,
)

urlpatterns = [
    path('dashboard/',      LaundryDashboardView.as_view(),  name='laundry_dashboard'),
    path('floor/',          ProcessingFloorView.as_view(),   name='laundry_floor'),
    path('floor/update/',   UpdateItemStageView.as_view(),   name='laundry_update_stage'),
    path('orders/',         LaundryOrderListView.as_view(),  name='laundry_order_list'),
    path('pricing/',        PricingView.as_view(),           name='laundry_pricing'),
    path('workers/',        WorkerManagementView.as_view(),  name='laundry_workers'),
    path('alerts/',         AlertsView.as_view(),            name='laundry_alerts'),
]
