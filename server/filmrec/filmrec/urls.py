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


from api.views.auth_views import (
    loginView, registerView, ping, 
    password_reset_confirm, password_reset_request)

from api.views.stats_views import stats_payload, stats_all_time

from api.views.import_views import manual_import, import_rss, onboarding_status
from api.views.profile_views import *

from api.views.tmdb_views import tmdb_search, tmdb_ensure

from api.views.chat_views import chat_recommend
from api.views.filmbank_views import film_bank_delete, film_bank_list

urlpatterns = [
    path("admin/", admin.site.urls),

    # User account related endppints
    path("api/login/", loginView, name="login"),
    path("api/register/", registerView, name="register"),

    path("api/profile/", profileView, name="profile"),
    
    # Check if User is onboarded 
    path("api/onboarding-status/", onboarding_status, name="onboarding-status"),\
    
    # Data ingestion endpoints
    path("api/import/csv/", manual_import, name="import-csv"),
    path("api/import/rss/", import_rss, name="import-rss"),
    
    path("api/password-reset/", password_reset_request, name="password_reset"),
    path("api/password-reset-confirm/", password_reset_confirm, name="password-reset-confirm"),

    # for authentication anything passing the login/registration
    path("api/ping/", ping, name="ping"),

    # Stats related endpoints
    path("api/stats/weekly/", stats_payload, name="stats-payload"),
    path("api/stats/all-time/", stats_all_time, name="stats-all-time"),

    # Chat Related endpoints
    path("api/tmdb/search/", tmdb_search),
    path("api/tmdb/ensure/", tmdb_ensure),
    path("api/chat/recommend/", chat_recommend),

    # Film Bank related endpoints
    path("api/film-bank/", film_bank_list, name="film-bank-list"),
    path("api/film-bank/<int:movie_id>/", film_bank_delete,name="film_bank_delete"),

]
