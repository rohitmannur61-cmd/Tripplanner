"""
URL configuration for tripplanner project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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

from planner import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("", views.home, name="home"),
    path("history/", views.history, name="history"),
    path("history/search/delete/<int:history_id>/", views.delete_search_history, name="delete_search_history"),
    path("history/search/clear/", views.clear_search_history, name="clear_search_history"),
    path("history/budget/delete/<int:history_id>/", views.delete_budget_history, name="delete_budget_history"),
    path("history/budget/clear/", views.clear_budget_history, name="clear_budget_history"),
    path("history/trip/delete/<int:trip_id>/", views.delete_trip_history, name="delete_trip_history"),
    path("history/trip/clear/", views.clear_trip_history, name="clear_trip_history"),
    path("trip/", views.trip, name="trip"),
    path("create_trip/", views.create_trip, name="create_trip"),
    path("hotel_prices/", views.hotel_prices_api, name="hotel_prices"),
    path("logout/", views.logout_view, name="logout"),
    path("expense/", views.expense_overview, name="expense_overview"),
    path("trip/<int:trip_id>/expense/", views.expense, name="expense"),
    path(
        "trip/<int:trip_id>/expense/delete/<int:expense_id>/",
        views.delete_expense,
        name="delete_expense",
    ),
    path(
        "trip/<int:trip_id>/members/delete/<int:member_id>/",
        views.delete_member,
        name="delete_member",
    ),
    path(
        "trip/<int:trip_id>/payments/delete/<int:settlement_id>/",
        views.delete_settlement,
        name="delete_settlement",
    ),
    path(
        "trip/<int:trip_id>/expense/export/",
        views.export_expenses,
        name="export_expenses",
    ),
]
from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
