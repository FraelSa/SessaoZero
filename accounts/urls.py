from django.urls import path

from . import views

urlpatterns = [
    path("cadastro/", views.cadastro, name="cadastro"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("confirmar-email/<str:token>/", views.confirmar_email, name="confirmar_email"),
    path("reenviar-confirmacao/", views.reenviar_confirmacao, name="reenviar_confirmacao"),
    path("preferencias/", views.editar_preferencias, name="editar_preferencias"),
    path("perfil/", views.editar_perfil, name="editar_perfil"),
    path("avatar/<path:username>/", views.avatar_usuario, name="avatar_usuario"),
    path(
        "recuperar-senha/",
        views.solicitar_recuperacao_senha,
        name="solicitar_recuperacao_senha",
    ),
    path(
        "redefinir-senha/<str:token>/",
        views.redefinir_senha,
        name="redefinir_senha",
    ),
]
