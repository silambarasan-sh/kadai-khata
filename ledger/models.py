from decimal import Decimal
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    """A customer who transacts with the shopkeeper on credit / cash."""

    name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self) -> str:
        if self.phone:
            return f"{self.name} ({self.phone})"
        return self.name


class EntryKind(models.TextChoices):
    CREDIT_GIVEN = "credit_given", "Credit Given (Udhaar)"
    PAYMENT_RECEIVED = "payment_received", "Payment Received (Varavu)"


class LedgerEntry(models.Model):
    """An individual credit or payment transaction recorded in the ledger."""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="entries"
    )
    kind = models.CharField(
        max_length=30,
        choices=EntryKind.choices,
        db_index=True
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    note = models.TextField(blank=True, default="")
    source_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"

    def __str__(self) -> str:
        return f"{self.customer.name} - {self.get_kind_display()}: ₹{self.amount}"
