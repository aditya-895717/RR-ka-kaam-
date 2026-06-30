from django.urls import path

from . import api

urlpatterns = [
    path('scan/s1/',                              api.S1ScanAPI.as_view(),             name='rfid_scan_s1'),
    path('scan/s2/',                              api.S2ScanAPI.as_view(),             name='rfid_scan_s2'),
    path('scan/s3/',                              api.S3ScanAPI.as_view(),             name='rfid_scan_s3'),
    path('scan/s4/',                              api.S4ScanAPI.as_view(),             name='rfid_scan_s4'),
    path('tag/<str:tag_number>/history/',         api.TagHistoryAPI.as_view(),         name='rfid_tag_history_api'),
    path('order/<uuid:order_id>/reconciliation/', api.OrderReconciliationAPI.as_view(), name='rfid_order_reconciliation'),
]
