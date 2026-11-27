from django.urls import path

from . import views

urlpatterns = [
    path("", views.listar_campanhas, name="listar_campanhas"),
    path("recomendadas/", views.campanhas_recomendadas, name="campanhas_recomendadas"),
    path("minhas/", views.minhas_campanhas, name="minhas_campanhas"),
    path("inscricoes/", views.minhas_inscricoes, name="minhas_inscricoes"),
    path("nova/", views.criar_campanha, name="criar_campanha"),
    path("<str:campanha_id>/", views.detalhe_campanha, name="detalhe_campanha"),
    path("<str:campanha_id>/editar/", views.editar_campanha, name="editar_campanha"),
    path("<str:campanha_id>/excluir/", views.excluir_campanha, name="excluir_campanha"),
    path("<str:campanha_id>/inscrever/", views.inscrever_campanha, name="inscrever_campanha"),
    path("<str:campanha_id>/sair/", views.sair_da_campanha, name="sair_da_campanha"),
    path("<str:campanha_id>/encerrar/", views.encerrar_campanha, name="encerrar_campanha"),
    path("<str:campanha_id>/reabrir/", views.reabrir_campanha, name="reabrir_campanha"),
    path("<str:campanha_id>/comentar/", views.comentar_campanha, name="comentar_campanha"),
    path(
        "<str:campanha_id>/avaliar/<str:username>/",
        views.avaliar_participante,
        name="avaliar_participante",
    ),
]
