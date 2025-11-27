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
    path('minijuego/', views.mine_game, name='mine_game'),
]
