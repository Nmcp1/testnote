from django.urls import re_path
from .consumers import ExpeditionConsumer

websocket_urlpatterns = [
    re_path(r"ws/expediciones/(?P<lobby_id>\d+)/$", ExpeditionConsumer.as_asgi()),
]
