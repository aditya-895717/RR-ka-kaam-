from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        """Connect an incoming social login to an existing account with the same email."""
        if sociallogin.is_existing:
            return
        if not sociallogin.email_addresses:
            return
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            email = sociallogin.email_addresses[0].email
            user = User.objects.get(email=email)
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not getattr(user, 'full_name', None):
            user.full_name = data.get('name', '')
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if hasattr(user, 'is_onboarded'):
            user.is_onboarded = False
            user.save(update_fields=['is_onboarded'])
        return user

    def get_signup_form_initial_data(self, sociallogin):
        data = super().get_signup_form_initial_data(sociallogin)
        data.pop('username', None)
        return data
