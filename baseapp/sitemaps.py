from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return [
            "home:home",
            "home:about",
            "home:contact",
            "account:register",
            "account:login",
        ]

    def location(self, item):
        return reverse(item)
