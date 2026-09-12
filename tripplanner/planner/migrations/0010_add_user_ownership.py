from django.conf import settings
from django.db import migrations, models


def assign_existing_records_to_single_user(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    SearchHistory = apps.get_model("planner", "SearchHistory")
    BudgetHistory = apps.get_model("planner", "BudgetHistory")
    Trip = apps.get_model("planner", "Trip")

    if User.objects.count() != 1:
        return

    owner = User.objects.first()
    SearchHistory.objects.filter(owner__isnull=True).update(owner=owner)
    BudgetHistory.objects.filter(owner__isnull=True).update(owner=owner)
    Trip.objects.filter(owner__isnull=True).update(owner=owner)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("planner", "0009_budgethistory_searchhistory"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgethistory",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="budget_history",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="searchhistory",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="search_history",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="trip",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="trips",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_existing_records_to_single_user, migrations.RunPython.noop),
    ]
