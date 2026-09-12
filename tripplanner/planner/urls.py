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
from django.urls import path
from planner import views
urlpatterns = [
    path('', views.home, name='home'),
    path('trip/', views.trip, name='trip'),
    path('trip/<int:trip_id>/expense/', views.expense, name='expense'),
    path('trip/<int:trip_id>/expense/export/', views.export_expenses, name='export_expenses'),
    path('trip/<int:trip_id>/expense/delete/<int:expense_id>/', views.delete_expense, name='delete_expense'),
    path('trip/<int:trip_id>/member/delete/<int:member_id>/', views.delete_member, name='delete_member'),
    path('trip/<int:trip_id>/settlement/delete/<int:settlement_id>/', views.delete_settlement, name='delete_settlement'),
    path('create_trip/', views.create_trip, name='create_trip'),
    path('hotel_prices/', views.hotel_prices_api, name='hotel_prices_api'),
]
