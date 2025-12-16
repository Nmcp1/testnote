from django.urls import path
from . import views

urlpatterns = [
    path("", views.expeditions_hub, name="expeditions_hub"),
    path("create/", views.create_lobby, name="expeditions_create"),
    path("join/<int:lobby_id>/", views.join_lobby, name="expeditions_join"),
    path("lobby/<int:lobby_id>/", views.lobby_view, name="expeditions_lobby"),
    path("start/<int:lobby_id>/", views.start_expedition, name="expeditions_start"),
    path("top/", views.expeditions_daily_top, name="expeditions_daily_top"),
]
