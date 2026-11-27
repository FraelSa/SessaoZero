from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("contas/", include("accounts.urls")),
    path("campanhas/", include("campanhas.urls")),
    path("notificacoes/", include("notificacoes.urls")),
    path("chat/", include("chat.urls")),
    path("moderacao/", include("moderacao.urls")),
]

# RNF06 - páginas de erro que não dependem do banco (ver core/views.py).
handler500 = "core.views.erro_500"
