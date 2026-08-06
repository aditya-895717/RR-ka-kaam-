import random
import string

from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views import View

from .models import (
    User, EmailOTP, Role,
    HospitalProfile, HospitalStaffProfile,
    LaundryProfile, LaundryWorkerProfile,
    DeliveryProfile,
)
from .forms import (
    HospitalHeadOnboardingForm, HospitalStaffOnboardingForm,
    LaundryAdminOnboardingForm, LaundryWorkerOnboardingForm,
    DeliveryPartnerOnboardingForm,
)
from notifications.brevo import send_otp_email, send_email


# ─── Auth views ──────────────────────────────────────────────────────────────

class SignupView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('account_redirect')
        return render(request, 'accounts/signup.html')

    def post(self, request):
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        errors = {}
        if not full_name:
            errors['full_name'] = 'Full name is required.'
        if not email:
            errors['email'] = 'Email address is required.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        if not password1:
            errors['password1'] = 'Password is required.'
        elif len(password1) < 8:
            errors['password1'] = 'Password must be at least 8 characters.'
        if password1 and password1 != password2:
            errors['password2'] = 'Passwords do not match.'

        if errors:
            return render(request, 'accounts/signup.html', {
                'errors': errors,
                'form_data': {'full_name': full_name, 'email': email},
            })

        user = User.objects.create_user(email=email, password=password1, full_name=full_name)
        _send_welcome_email(user)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('/accounts/onboarding/')


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('account_redirect')
        return render(request, 'accounts/login.html')

    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('account_redirect')
        return render(request, 'accounts/login.html', {
            'error': 'Invalid email or password.',
            'active_tab': 'password',
            'form_data': {'email': email},
        })


class OTPRequestView(View):
    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        if not email:
            return JsonResponse({'success': False, 'error': 'Email is required.'})
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'No account found with this email.'})
        otp_code = ''.join(random.choices(string.digits, k=6))
        EmailOTP.objects.create(user=user, otp_code=otp_code)
        sent = send_otp_email(email, user.full_name, otp_code)
        if not sent:
            return JsonResponse({'success': False, 'error': 'Could not send OTP email. Please try again.'})
        return JsonResponse({'success': True})


class OTPVerifyView(View):
    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        otp_code = request.POST.get('otp_code', '').strip()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid email.'})

        otp = (
            EmailOTP.objects
            .filter(user=user, otp_code=otp_code, is_used=False)
            .order_by('-created_at')
            .first()
        )
        if otp is None or not otp.is_valid():
            return JsonResponse({'success': False, 'error': 'Invalid or expired OTP. Please request a new one.'})

        otp.is_used = True
        otp.save(update_fields=['is_used'])
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({'success': True, 'redirect': '/accounts/redirect/'})


@method_decorator(login_required, name='dispatch')
class RoleRedirectView(View):
    def get(self, request):
        user = request.user
        if not user.is_onboarded:
            return redirect('/accounts/onboarding/')
        role = user.role
        if role in ('HOSPITAL_HEAD', 'HOSPITAL_STAFF'):
            return redirect('/hospital/dashboard/')
        if role in ('LAUNDRY_ADMIN', 'LAUNDRY_WORKER'):
            return redirect('/laundry/dashboard/')
        if role == 'DELIVERY_PARTNER':
            return redirect('/delivery/dashboard/')
        return redirect('/accounts/onboarding/')


# ─── Onboarding ──────────────────────────────────────────────────────────────

_PROFILE_FORMS = {
    Role.HOSPITAL_HEAD:    HospitalHeadOnboardingForm,
    Role.HOSPITAL_STAFF:   HospitalStaffOnboardingForm,
    Role.LAUNDRY_ADMIN:    LaundryAdminOnboardingForm,
    Role.LAUNDRY_WORKER:   LaundryWorkerOnboardingForm,
    Role.DELIVERY_PARTNER: DeliveryPartnerOnboardingForm,
}

_ROLE_LABELS = dict(Role.choices)

_SESSION_STEP = 'onboarding_step'
_SESSION_ROLE = 'onboarding_role'


@method_decorator(login_required, name='dispatch')
class OnboardingView(View):
    def get(self, request):
        if request.user.is_onboarded:
            return redirect('account_redirect')

        # "Back" link from step 2 restarts the flow
        if 'restart' in request.GET:
            request.session.pop(_SESSION_STEP, None)
            request.session.pop(_SESSION_ROLE, None)
            return redirect('account_onboarding')

        step = int(request.session.get(_SESSION_STEP, 1))
        role = request.session.get(_SESSION_ROLE, '')

        ctx = {'step': step, 'role': role, 'role_label': _ROLE_LABELS.get(role, '')}
        if step == 2 and role in _PROFILE_FORMS:
            ctx['profile_form'] = _PROFILE_FORMS[role]()
        return render(request, 'accounts/onboarding.html', ctx)

    def post(self, request):
        step = request.POST.get('step', '1')
        if step == '1':
            return self._handle_step1(request)
        return self._handle_step2(request)

    # ── step 1: role selection ──
    def _handle_step1(self, request):
        role = request.POST.get('role', '')
        if role not in _PROFILE_FORMS:
            return render(request, 'accounts/onboarding.html', {
                'step': 1,
                'error': 'Please select a role to continue.',
            })
        if role in (Role.HOSPITAL_STAFF, Role.LAUNDRY_WORKER):
            return render(request, 'accounts/onboarding.html', {
                'step': 1,
                'error': (
                    'Staff and Worker accounts are created by your admin — '
                    'ask your Hospital Head or Laundry Admin to add you.'
                ),
            })
        request.session[_SESSION_STEP] = 2
        request.session[_SESSION_ROLE] = role
        return render(request, 'accounts/onboarding.html', {
            'step': 2,
            'role': role,
            'role_label': _ROLE_LABELS[role],
            'profile_form': _PROFILE_FORMS[role](),
        })

    # ── step 2: profile details ──
    def _handle_step2(self, request):
        role = request.session.get(_SESSION_ROLE, '')
        if not role or role not in _PROFILE_FORMS:
            request.session.pop(_SESSION_STEP, None)
            return redirect('account_onboarding')

        form = _PROFILE_FORMS[role](request.POST)
        if not form.is_valid():
            return render(request, 'accounts/onboarding.html', {
                'step': 2,
                'role': role,
                'role_label': _ROLE_LABELS[role],
                'profile_form': form,
            })

        _save_profile(request.user, role, form.cleaned_data)

        user = request.user
        user.role = role
        user.is_onboarded = True
        if form.cleaned_data.get('phone_number'):
            user.phone_number = form.cleaned_data['phone_number']
        user.save(update_fields=['role', 'is_onboarded', 'phone_number'])

        request.session.pop(_SESSION_STEP, None)
        request.session.pop(_SESSION_ROLE, None)
        return redirect('account_redirect')


def _save_profile(user, role, data):
    """Persist the role-specific profile record for the given user."""
    if role == Role.HOSPITAL_HEAD:
        HospitalProfile.objects.create(
            user=user,
            hospital_name=data['hospital_name'],
            hospital_address=data['hospital_address'],
            city=data['city'],
            area=data['area'],
            phone_number=data['phone_number'],
        )
    elif role == Role.HOSPITAL_STAFF:
        HospitalStaffProfile.objects.create(
            user=user,
            hospital=data['hospital'],
            department=data.get('department'),
            phone_number=data['phone_number'],
        )
    elif role == Role.LAUNDRY_ADMIN:
        LaundryProfile.objects.create(
            user=user,
            business_name=data['business_name'],
            address=data['address'],
            city=data['city'],
            area=data['area'],
            phone_number=data['phone_number'],
            price_per_item=data['price_per_item'],
        )
    elif role == Role.LAUNDRY_WORKER:
        LaundryWorkerProfile.objects.create(
            user=user,
            laundry=data['laundry'],
            phone_number=data['phone_number'],
        )
    elif role == Role.DELIVERY_PARTNER:
        DeliveryProfile.objects.create(
            user=user,
            city=data['city'],
            area=data['area'],
            phone_number=data['phone_number'],
            vehicle_type=data.get('vehicle_type', ''),
        )


# ─── Misc views ───────────────────────────────────────────────────────────────

def logout_view(request):
    auth_logout(request)
    return redirect('index')


def _send_welcome_email(user):
    name    = user.full_name or 'there'
    subject = 'Welcome to RRLaundry'
    html    = f"""
<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;">
  <h2 style="color:#003580;margin-bottom:8px;">Welcome to RRLaundry, {name}!</h2>
  <p style="color:#555;">Your account has been created successfully.</p>
  <p style="color:#555;">Complete your profile setup to get started managing
     laundry operations.</p>
  <hr style="border:none;border-top:1px solid #eee;margin:28px 0 16px;">
  <p style="color:#bbb;font-size:11px;text-align:center;margin:0;">
    Dubey IT Solutions — RRLaundry
  </p>
</div>"""
    send_email(user.email, user.full_name, subject, html)
