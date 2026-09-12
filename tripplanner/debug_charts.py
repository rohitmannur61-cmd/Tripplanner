import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tripplanner.settings')
django.setup()

from planner.models import Expense, Trip, Member, Settlement

print("=== ALL TRIPS ===")
for t in Trip.objects.all().order_by('id'):
    members = list(Member.objects.filter(trip=t))
    expenses = list(Expense.objects.filter(trip=t))
    settlements = list(Settlement.objects.filter(trip=t))
    member_names = [m.name for m in members]
    print(f"  Trip ID={t.id} | name={repr(t.trip_name)} | members={member_names} | expenses={len(expenses)} | settlements={len(settlements)}")
    for e in expenses:
        print(f"    EXPENSE: {e.category} | {e.description} | amt={e.amount}")
    for s in settlements:
        print(f"    SETTLEMENT: {s.payer.name} paid {s.payee.name} = {s.amount}")
