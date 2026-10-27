from django.urls import path
from . import views

app_name = "ledger"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/parse/", views.api_parse, name="api_parse"),
    path("api/confirm/", views.api_confirm, name="api_confirm"),
    path("api/reject/", views.api_reject, name="api_reject"),
    path("api/customers/", views.api_customers, name="api_customers"),
    path("api/customers/<int:customer_id>/timeline/", views.api_customer_timeline, name="api_customer_timeline"),
    path("api/reverse/", views.api_reverse, name="api_reverse"),
    path("api/reminder/", views.api_reminder, name="api_reminder"),
]
