from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("status/mongo/", views.status_mongo, name="status_mongo"),
]
