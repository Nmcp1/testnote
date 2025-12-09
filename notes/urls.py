from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('privadas/', views.private_notes, name='private_notes'),
    path('like/<int:note_id>/', views.toggle_like, name='toggle_like'),
    path('nota/<int:note_id>/', views.note_detail, name='note_detail'),
    path('notificaciones/', views.notifications, name='notifications'),
    path('moderacion/codigos/', views.invitation_admin, name='invitation_admin'),
    path('moderacion/moderadores/', views.moderator_panel, name='moderator_panel'),

    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('minas/', views.mine_game, name='mine_game'),

    path('rpg/', views.rpg_hub, name='rpg_hub'),
    path('rpg/tienda/', views.rpg_shop, name='rpg_shop'),
    path('rpg/gacha/', views.rpg_gacha, name='rpg_gacha'),
    path('rpg/torre/', views.rpg_tower, name='rpg_tower'),
    path('rpg/inventario/', views.rpg_inventory, name='rpg_inventory'),
    path('rpg/gacha/config/', views.rpg_gacha_config, name='rpg_gacha_config'),
    path('rpg/gacha/config/premium/', views.rpg_gacha_premium_config, name='rpg_gacha_premium_config'),
    path("rpg/pvp/", views.rpg_pvp_arena, name="rpg_pvp_arena"),
    path("rpg/pvp/challenge/<int:target_id>/", views.rpg_pvp_challenge, name="rpg_pvp_challenge"),
    path("rpg/pvp/leaderboard/", views.rpg_pvp_leaderboard, name="rpg_pvp_leaderboard"),
    path("rpg/trades/", views.rpg_trades, name="rpg_trades"),
    path("rpg/trades/new/", views.rpg_trade_create, name="rpg_trade_create"),
    path("rpg/trades/<int:trade_id>/", views.rpg_trade_detail, name="rpg_trade_detail"),
    path('rpg/world-boss/', views.rpg_world_boss, name='rpg_world_boss'),
    path('rpg/miniboss/', views.rpg_miniboss_hub, name='rpg_miniboss_hub'),
    path('rpg/miniboss/<int:lobby_id>/', views.rpg_miniboss_lobby, name='rpg_miniboss_lobby'),

    path("rpg/market/", views.rpg_market, name="rpg_market"),
    path("rpg/market/list/<int:item_id>/", views.rpg_market_list_item, name="rpg_market_list_item"),
    path("rpg/market/cancel/<int:listing_id>/", views.rpg_market_cancel, name="rpg_market_cancel"),
    path("rpg/market/buy/<int:listing_id>/", views.rpg_market_buy, name="rpg_market_buy"),

    path("rpg/vip-shop/", views.rpg_vip_shop, name="rpg_vip_shop"),
    path("rpg/vip-admin/", views.rpg_vip_admin, name="rpg_vip_admin"),
    path("rpg/sorteo/", views.rpg_raffle, name="rpg_raffle"),

    
]
