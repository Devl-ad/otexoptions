# dashboard/routing.py

from django.urls import re_path
from dashboard import consumers

websocket_urlpatterns = [
    re_path(r"^ws/price/(?P<symbol>\w+)/$", consumers.PriceConsumer.as_asgi()),
    re_path(r"^ws/trades/$", consumers.TradeConsumer.as_asgi()),
    re_path(r"^ws/bot/$", consumers.BotConsumer.as_asgi()),
]
