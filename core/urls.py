from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("privacidade/", views.politica_privacidade, name="politica_privacidade"),
    path("status/mongo/", views.status_mongo, name="status_mongo"),
    path("saude/", views.saude, name="saude"),
    path("saude/banco/", views.saude_do_banco, name="saude_do_banco"),
]
