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
    path("api/agent/run/", views.api_agent_run, name="api_agent_run"),
    path("api/agent/run/<int:run_id>/", views.api_agent_run_detail, name="api_agent_run_detail"),
    path("api/agent/approve/", views.api_agent_approve, name="api_agent_approve"),
    path("api/ask/", views.api_ask, name="api_ask"),
    path("api/parse-photo/", views.api_parse_photo, name="api_parse_photo"),
]

