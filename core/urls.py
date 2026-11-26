from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("privacidade/", views.politica_privacidade, name="politica_privacidade"),
    path("status/mongo/", views.status_mongo, name="status_mongo"),
]
