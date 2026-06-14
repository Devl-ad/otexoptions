from django.apps import AppConfig


class Accountconfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.account"
    verbose_name = "Account"

    def ready(self):
        import apps.account.signals
