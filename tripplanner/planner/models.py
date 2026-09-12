from django.conf import settings
from django.db import models


class Trip(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trips",
        null=True,
        blank=True,
    )
    trip_name = models.CharField(max_length=100)

    def __str__(self):
        return self.trip_name


class Member(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class SearchHistory(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_history",
        null=True,
        blank=True,
    )
    place = models.CharField(max_length=200)
    raw_query = models.CharField(max_length=200)
    image = models.URLField(blank=True, max_length=500)
    desc = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.place


class BudgetHistory(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budget_history",
        null=True,
        blank=True,
    )
    place = models.CharField(blank=True, max_length=200)
    cover_image = models.URLField(blank=True, max_length=500)
    description = models.TextField(blank=True)
    people = models.PositiveIntegerField(default=1)
    days = models.PositiveIntegerField(default=1)
    hotel_per_night = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    food_per_day = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    travel = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    activities = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    misc = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    contingency_pct = models.DecimalField(decimal_places=2, default=0, max_digits=5)
    hotel_total = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    food_total = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    base_total = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    contingency = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    total = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    per_person = models.DecimalField(decimal_places=2, default=0, max_digits=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.place or 'Trip'} budget - {self.total}"


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ("Hotel", "Hotel"),
        ("Food", "Food"),
        ("Travel", "Travel"),
        ("Activities", "Activities"),
        ("Misc", "Misc"),
    ]
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    paid_by = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="expenses_paid")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="Misc")
    description = models.CharField(max_length=200)
    receipt_image = models.ImageField(upload_to="receipts/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    members_involved = models.ManyToManyField(Member, related_name="expenses_involved_in", blank=True)

    def __str__(self):
        involved_names = (
            ", ".join([m.name for m in self.members_involved.all()])
            if self.members_involved.exists()
            else "All members"
        )
        return f"{self.paid_by.name} paid Rs{self.amount} for {self.description} (for: {involved_names})"


class Settlement(models.Model):
    """
    Records a repayment between members (e.g. B pays A 500).
    This lets balances change over time as people settle up.
    """

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="settlements")
    payer = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="settlements_paid")
    payee = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="settlements_received")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.payer.name} paid Rs{self.amount} to {self.payee.name}"
