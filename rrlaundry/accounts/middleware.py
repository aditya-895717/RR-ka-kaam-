from django.shortcuts import redirect

_ONBOARDING_URL = '/accounts/onboarding/'

_EXEMPT_PREFIXES = (
    '/accounts/',   # all auth + onboarding paths
    '/admin/',
    '/static/',
    '/media/',
)


class OnboardingRedirectMiddleware:
    """Redirect authenticated-but-not-onboarded users to the onboarding flow."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and not user.is_onboarded
            and not any(request.path.startswith(p) for p in _EXEMPT_PREFIXES)
        ):
            return redirect(_ONBOARDING_URL)
        return self.get_response(request)
