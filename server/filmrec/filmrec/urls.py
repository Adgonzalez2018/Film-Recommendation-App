"""
URL configuration for filmrec project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path


from api.views.auth_views import loginView, registerView, ping, password_reset_confirm, password_reset_request
from api.views.stats_views import stats_payload, stats_all_time
from api.views.letterboxd_views import letterboxd_import, letterboxd_rss

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/login/", loginView, name="login"),
    path("api/register/", registerView, name="register"),

    path("api/password-reset/", password_reset_request, name="password_reset"),
    path("api/password-reset-confirm/", password_reset_confirm, name="password-reset-confirm"),

    # for authentication anything passing the login/registration
    path("api/ping/", ping, name="ping"),
    path("api/stats/", stats_payload, name="stats-payload"),
    path("api/stats/all-time", stats_all_time, name="stats-all-time"),


    path("api/letterboxd/import/", letterboxd_import, name="letterboxd-import"),
    path("api/letterboxd/rss/", letterboxd_rss, name="letterboxd-rss"),
]
