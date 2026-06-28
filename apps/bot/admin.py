# dashboard/admin.py
from django.db import models
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from apps.bot.models import BotKey, BotTrade, BotSession, BotTemplate


@admin.register(BotTemplate)
class BotTemplateAdmin(ModelAdmin):
    list_display = [
        "name",
    ]

    list_per_page = 25
    list_max_show_all = 200


@admin.register(BotTrade)
class BotTradeAdmin(ModelAdmin):
    list_display = ["session", "result"]
    list_per_page = 25
    list_max_show_all = 200  # cap for "show all" link


@admin.register(BotSession)
class BotSessionAdmin(ModelAdmin):
    list_display = ["id", "user", "pair"]
    search_fields = ("user__username", "bot_key__key", "pair__symbol")
    list_per_page = 25
    list_max_show_all = 200  # cap for "show all" link


@admin.register(BotKey)
class BotKeyAdmin(ModelAdmin):
    list_display = ["key", "label"]
    list_editable = ["label"]
    search_fields = ("key", "label")
    list_per_page = 25
    list_max_show_all = 200  # cap for "show all" link

    ieldsets = (
        (
            "Bot Info",
            {
                "fields": (
                    "name",
                    "bot_type",
                    "profit_pct",
                    "description",
                    "is_active",
                )
            },
        ),
        (
            "Demo Mode Settings",
            {
                "fields": (
                    "demo_base_win_rate",
                    "demo_house_outcome",
                    "demo_breakeven_min_pct",
                    "demo_breakeven_max_pct",
                ),
                "description": "More generous settings to encourage users to go live.",
            },
        ),
        (
            "Live Mode Settings",
            {
                "fields": (
                    "base_win_rate",
                    "house_outcome",
                    "breakeven_min_pct",
                    "breakeven_max_pct",
                ),
                "description": "Real house edge — controls actual revenue.",
            },
        ),
    )
