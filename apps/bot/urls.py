from django.urls import path
from . import views

app_name = "bot"

urlpatterns = [
    path("", views.bot_page, name="bot_page"),
    path("validate-key/", views.validate_bot_key, name="validate_key"),
    path("load-botemplate/", views.laod_bot_template, name="laod_bot_template"),
    path("templates/", views.list_templates, name="list_templates"),
    path("templates/save/", views.save_template, name="save_template"),
    path("start/", views.start_bot, name="start_bot"),
    path("summary/<uuid:session_id>/", views.session_summary, name="session_summary"),
]
