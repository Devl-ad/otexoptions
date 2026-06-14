import os
import sys

# path must be set BEFORE django.setup()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "apps"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "baseapp.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import django

django.setup()

import dashboard.routing

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(dashboard.routing.websocket_urlpatterns)
        ),
    }
)
