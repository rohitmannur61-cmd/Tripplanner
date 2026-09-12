"""
0004 fixes the original "paid_by" CharField -> ForeignKey change so existing rows
in SQLite can be migrated safely.

The previous version of this migration attempted to:
- Alter paid_by to a ForeignKey directly (would fail with existing string data)
- Alter trip with an invalid default (timezone.now is not a Trip PK)

This updated migration:
- Ensures every Expense has a Trip (creates a default Trip only if needed)
- Creates Member rows from existing paid_by strings (per trip)
- Swaps the schema to the final FK field name "paid_by"
"""

from django.db import migrations, models
import django.db.models.deletion


def forwards_copy_paid_by(apps, schema_editor):
    Trip = apps.get_model("planner", "Trip")
    Member = apps.get_model("planner", "Member")
    Expense = apps.get_model("planner", "Expense")

    # If there are legacy expenses without a trip, attach them to a default trip.
    default_trip = None
    if Expense.objects.filter(trip__isnull=True).exists():
        default_trip, _ = Trip.objects.get_or_create(trip_name="Migrated Trip")
        Expense.objects.filter(trip__isnull=True).update(trip=default_trip)

    # Copy legacy Expense.paid_by (string) -> Expense.paid_by_member (FK).
    # Create Members as needed under each expense's trip.
    for expense in Expense.objects.all().only("id", "trip_id", "paid_by"):
        trip_id = expense.trip_id
        if trip_id is None:
            if default_trip is None:
                default_trip, _ = Trip.objects.get_or_create(trip_name="Migrated Trip")
            trip_id = default_trip.id
            Expense.objects.filter(id=expense.id).update(trip_id=trip_id)

        raw_name = getattr(expense, "paid_by", "") or ""
        name = raw_name.strip() or "Unknown"
        member, _ = Member.objects.get_or_create(trip_id=trip_id, name=name)
        Expense.objects.filter(id=expense.id).update(paid_by_member_id=member.id)


def backwards_noop(apps, schema_editor):
    # Non-reversible data migration (would require reconstructing strings).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0003_expense_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="members_involved",
            field=models.ManyToManyField(
                blank=True,
                related_name="expenses_involved_in",
                to="planner.member",
            ),
        ),
        migrations.AddField(
            model_name="expense",
            name="paid_by_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="expenses_paid",
                to="planner.member",
            ),
        ),
        migrations.RunPython(forwards_copy_paid_by, backwards_noop),
        migrations.RemoveField(
            model_name="expense",
            name="paid_by",
        ),
        migrations.RenameField(
            model_name="expense",
            old_name="paid_by_member",
            new_name="paid_by",
        ),
        migrations.AlterField(
            model_name="expense",
            name="paid_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="expenses_paid",
                to="planner.member",
            ),
        ),
        migrations.AlterField(
            model_name="expense",
            name="trip",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="planner.trip",
            ),
        ),
    ]
