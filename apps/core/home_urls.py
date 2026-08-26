from django.urls import path

from apps.core import home_views

app_name = "home"

urlpatterns = [
    path("", home_views.home, name="home"),
]
