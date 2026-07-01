# yourapp/tasks.py
from celery import shared_task
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from .email_templates import EMAIL_TEMPLATES

User = get_user_model()

import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, rate_limit="10/s")
def send_template_email_task(self, user_id, template_key, extra_context=None):
    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning(
            f"send_template_email_task: user {user_id} not found or inactive"
        )
        return

    if not user.email:
        logger.warning(f"send_template_email_task: user {user_id} has no email")
        return

    try:
        tpl = EMAIL_TEMPLATES[template_key]
        context = {"user": user, **(extra_context or {})}
        text_body = render_to_string(tpl["text_template"], context)
        html_body = render_to_string(tpl["html_template"], context)

        email = EmailMultiAlternatives(
            subject=tpl["subject"],
            body=text_body,
            from_email="info@otexoption.com",
            to=[user.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send()
        logger.info(f"Sent '{template_key}' email to {user.email}")
    except Exception as e:
        logger.error(
            f"Failed to send '{template_key}' to user {user_id}: {e}", exc_info=True
        )
        raise self.retry(exc=e, countdown=30)
