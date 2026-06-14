from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import account_activation_token, password_reset_token


def _send(subject, to_email, text_template, html_template, context):
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context)
    email = EmailMultiAlternatives(subject=subject, body=text_body, to=[to_email])
    email.attach_alternative(html_body, "text/html")
    email.send()


def send_activation_email(request, user):
    site = get_current_site(request)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    context = {
        "user": user,
        "domain": site.domain,
        "protocol": "https" if request.is_secure() else "http",
        "uid": uid,
        "token": token,
    }
    _send(
        subject="Welcome to OTEX – Please verify your email",
        to_email=user.email,
        text_template="account/emails/activation.txt",
        html_template="account/emails/activation.html",
        context=context,
    )


def send_password_reset_email(request, user):
    site = get_current_site(request)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_reset_token.make_token(user)
    context = {
        "user": user,
        "domain": site.domain,
        "protocol": "https" if request.is_secure() else "http",
        "uid": uid,
        "token": token,
    }
    _send(
        subject="OTEX – Reset Your Password",
        to_email=user.email,
        text_template="account/emails/password_reset.txt",
        html_template="account/emails/password_reset.html",
        context=context,
    )
