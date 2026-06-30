from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap
from .robots import robots_txt

sitemaps = {
    "static": StaticViewSitemap,
}


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.home.urls")),
    path("auth/", include("apps.account.urls"), name="auth"),
    path("dashboard/", include("apps.dashboard.urls")),
    path("bot/", include("apps.bot.urls")),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("robots.txt", robots_txt),
]
