from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.dashboard.models import Wallet

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Create a Wallet automatically whenever a new User is saved."""
    if created:
        Wallet.objects.get_or_create(user=instance)
