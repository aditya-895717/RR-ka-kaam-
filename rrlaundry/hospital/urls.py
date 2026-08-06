from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/',                                   views.HospitalDashboardView.as_view(),          name='hospital_dashboard'),
    path('partners/',                                    views.PartnerSelectionView.as_view(),            name='hospital_partners'),
    path('partners/change/',                             views.ChangePartnerView.as_view(),               name='hospital_change_partner'),
    path('partners/laundry/<int:partner_id>/',           views.LaundryPartnerProfileView.as_view(),       name='hospital_laundry_partner_profile'),
    path('partners/delivery/<int:partner_id>/',          views.DeliveryPartnerProfileView.as_view(),      name='hospital_delivery_partner_profile'),
    path('departments/',                                 views.DepartmentManagementView.as_view(),        name='hospital_departments'),
    path('orders/',                                      views.OrderListView.as_view(),                   name='hospital_order_list'),
    path('orders/new/',                                  views.NewOrderView.as_view(),                    name='hospital_new_order'),
    path('orders/<uuid:order_id>/',                      views.OrderDetailView.as_view(),                 name='hospital_order_detail'),
    path('orders/<uuid:order_id>/confirm/',              views.DeliveryConfirmationView.as_view(),        name='hospital_confirm_delivery'),
    path('tracking/',                                    views.ItemTrackingView.as_view(),                name='hospital_item_tracking'),
    path('staff/',                                       views.ManageStaffView.as_view(),                 name='hospital_manage_staff'),
    path('staff/<uuid:user_id>/deactivate/',             views.DeactivateStaffView.as_view(),             name='hospital_deactivate_staff'),
    path('staff/<uuid:user_id>/reactivate/',             views.ReactivateStaffView.as_view(),             name='hospital_reactivate_staff'),
]
