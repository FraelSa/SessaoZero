from django.urls import path

from . import views

urlpatterns = [
    path("", views.painel, name="painel_moderacao"),
    path("<str:bloqueio_id>/revisar/", views.revisar, name="revisar_bloqueio"),
]
