from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='account_signup'),
    path('login/', views.LoginView.as_view(), name='account_login'),
    path('logout/', views.logout_view, name='account_logout'),
    path('otp/request/', views.OTPRequestView.as_view(), name='account_otp_request'),
    path('otp/verify/', views.OTPVerifyView.as_view(), name='account_otp_verify'),
    path('redirect/', views.RoleRedirectView.as_view(), name='account_redirect'),
    path('onboarding/', views.OnboardingView.as_view(), name='account_onboarding'),
]
