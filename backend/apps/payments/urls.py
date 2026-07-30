"""Payment routes, mounted at /api/v1/payments/."""

from django.urls import path

from .views import (
    CancelOrderView,
    CreateOrderView,
    MyPurchasesView,
    QuoteView,
    VerifyView,
    WebhookView,
)

app_name = "payments"

urlpatterns = [
    path("quote/", QuoteView.as_view(), name="quote"),
    path("create-order/", CreateOrderView.as_view(), name="create-order"),
    path("verify/", VerifyView.as_view(), name="verify"),
    path("cancel-order/", CancelOrderView.as_view(), name="cancel-order"),
    path("my-purchases/", MyPurchasesView.as_view(), name="my-purchases"),
    path("webhook/", WebhookView.as_view(), name="webhook"),
]
