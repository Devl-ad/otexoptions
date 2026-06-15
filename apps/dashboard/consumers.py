import logging
import json
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class PriceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.symbol = self.scope["url_route"]["kwargs"]["symbol"]
        self.group = f"price_{self.symbol}"

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        logger.info(f"❌ WebSocket disconnected: {self.symbol} code={code}")
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def price_update(self, event):
        try:
            await self.send(
                text_data=json.dumps(
                    {
                        "symbol": event["symbol"],
                        "price": event["price"],
                        "time": event["time"],
                        "type": "price_update",
                    }
                )
            )
        except Exception as e:
            logger.info(f"Send error: {e}")


class TradeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope["user"].id
        self.group = f"trade_{self.user_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def trade_result(self, event):
        await self.send(text_data=json.dumps(event))


class BotConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        self.user_id = self.scope["user"].id
        self.group_name = f"bot_{self.user_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def bot_trade_open(self, event):
        """Trade just opened — show as Running in feed."""
        await self.send(text_data=json.dumps({"type": "bot_trade_open", **event}))

    async def bot_trade_result(self, event):
        """Trade resolved — update row to WON/LOST."""
        await self.send(text_data=json.dumps({"type": "bot_trade_result", **event}))

    async def bot_session_complete(self, event):
        """All trades done."""
        await self.send(text_data=json.dumps({"type": "bot_session_complete", **event}))
