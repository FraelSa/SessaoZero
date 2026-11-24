from django.urls import path

from . import views

urlpatterns = [
    path("", views.listar_notificacoes, name="listar_notificacoes"),
    path("<str:notificacao_id>/ir/", views.ir_para_notificacao, name="ir_para_notificacao"),
]
