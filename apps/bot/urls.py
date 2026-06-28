from django.urls import path
from . import views

urlspattern = [
    path("ai-trading/", views.bot_page, name="ai_trading"),
    path("bot/validate-key/", views.validate_bot_key, name="validate_key"),
    path("bot/start/", views.start_bot, name="start_bot"),
    path(
        "bot/summary/<uuid:session_id>/", views.session_summary, name="session_summary"
    ),
]
