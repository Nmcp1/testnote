from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('privadas/', views.private_notes, name='private_notes'),
    path('like/<int:note_id>/', views.toggle_like, name='toggle_like'),
]
