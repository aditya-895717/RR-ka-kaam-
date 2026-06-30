from allauth.socialaccount.signals import social_account_added
from django.dispatch import receiver


@receiver(social_account_added)
def populate_full_name_from_social(sender, request, sociallogin, **kwargs):
    user = sociallogin.user
    if sociallogin.account.provider == 'google' and not user.full_name:
        user.full_name = sociallogin.account.extra_data.get('name', '')
        user.save(update_fields=['full_name'])
