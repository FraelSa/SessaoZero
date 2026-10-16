from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("contas/", include("accounts.urls")),
    path("campanhas/", include("campanhas.urls")),
    path("notificacoes/", include("notificacoes.urls")),
    path("chat/", include("chat.urls")),
]
