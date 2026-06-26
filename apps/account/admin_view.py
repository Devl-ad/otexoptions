# apps/dashboard/admin_views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.decorators import method_decorator

from .analytics import get_platform_analytics
from .models import PlatformSettings


@staff_member_required
def platform_analytics_view(request):
    if request.method == "POST":
        new_target = request.POST.get("target_market_cap")
        new_threshold = request.POST.get("safety_threshold_pct")

        settings_obj = PlatformSettings.load()
        try:
            if new_target:
                settings_obj.target_market_cap = new_target
            if new_threshold:
                settings_obj.safety_threshold_pct = new_threshold
            settings_obj.save()
            messages.success(request, "Platform settings updated.")
        except Exception as e:
            messages.error(request, f"Failed to update settings: {e}")

        return redirect("admin:platform_analytics")

    data = get_platform_analytics()

    context = {
        **admin.site.each_context(request),
        "title": "Platform Analytics",
        "data": data,
        "settings_obj": PlatformSettings.load(),
    }
    return render(request, "admin/platform_analytics.html", context)
