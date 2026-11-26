from django.urls import path

from . import views

urlpatterns = [
    path("", views.listar_campanhas, name="listar_campanhas"),
    path("recomendadas/", views.campanhas_recomendadas, name="campanhas_recomendadas"),
    path("inscricoes/", views.minhas_inscricoes, name="minhas_inscricoes"),
    path("nova/", views.criar_campanha, name="criar_campanha"),
    path("<str:campanha_id>/", views.detalhe_campanha, name="detalhe_campanha"),
    path("<str:campanha_id>/editar/", views.editar_campanha, name="editar_campanha"),
    path("<str:campanha_id>/excluir/", views.excluir_campanha, name="excluir_campanha"),
    path("<str:campanha_id>/inscrever/", views.inscrever_campanha, name="inscrever_campanha"),
    path("<str:campanha_id>/comentar/", views.comentar_campanha, name="comentar_campanha"),
    path(
        "<str:campanha_id>/avaliar/<str:username>/",
        views.avaliar_participante,
        name="avaliar_participante",
    ),
]
