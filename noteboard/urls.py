# noteboard/urls.py
from django.contrib import admin
from django.urls import path, include
from notes.views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),  # página principal con el muro de notas
    path('notes/', include('notes.urls')),  # registro, etc.
    path('accounts/', include('django.contrib.auth.urls')),  # login, logout, password_reset, etc.
]
