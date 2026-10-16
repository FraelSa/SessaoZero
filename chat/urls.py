from django.urls import path

from . import views

urlpatterns = [
    path("<str:campanha_id>/", views.sala_chat, name="sala_chat"),
]
