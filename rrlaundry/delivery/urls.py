from django.urls import path

from . import views

urlpatterns = [
    path('',          views.DeliveryDashboardView.as_view(), name='delivery_dashboard'),
    path('jobs/',     views.JobListView.as_view(),           name='delivery_job_list'),
    path('history/',  views.JobHistoryView.as_view(),        name='delivery_job_history'),
    path('scan/pickup/<uuid:job_id>/',   views.ScanPickupView.as_view(),   name='delivery_scan_pickup'),
    path('scan/delivery/<uuid:job_id>/', views.ScanDeliveryView.as_view(), name='delivery_scan_delivery'),
]
