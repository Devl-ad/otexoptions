# home/views.py

from django.http import HttpResponse


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Sitemap: https://www.otexoption.com/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
