from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import BudgetHistory, Expense, Member, SearchHistory, Settlement, Trip


class PlannerTestCase(TestCase):
    password = "StrongPass123!"

    def create_user(self, username="rohit", email=None, password=None):
        return User.objects.create_user(
            username=username,
            email=email or f"{username}@example.com",
            password=password or self.password,
        )

    def login_user(self, user=None):
        user = user or self.create_user()
        self.client.force_login(user)
        return user


class AuthFlowTests(PlannerTestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "rohit",
                "email": "rohit@example.com",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="rohit").exists())

        history_response = self.client.get(reverse("history"))
        self.assertEqual(history_response.status_code, 200)

    def test_anonymous_user_is_redirected_to_login_for_private_pages(self):
        response = self.client.get(reverse("history"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('history')}")

        response = self.client.get(reverse("trip"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('trip')}")


class DeleteMemberViewTests(PlannerTestCase):
    def setUp(self):
        self.user = self.login_user()
        self.trip = Trip.objects.create(owner=self.user, trip_name="Badami")
        self.member_to_delete = Member.objects.create(trip=self.trip, name="Rohit")
        self.other_member = Member.objects.create(trip=self.trip, name="Sudeep")

    def test_delete_member_removes_selected_member_and_related_records(self):
        expense = Expense.objects.create(
            trip=self.trip,
            paid_by=self.member_to_delete,
            amount=Decimal("1500.00"),
            description="Hotel",
        )
        expense.members_involved.add(self.member_to_delete, self.other_member)

        Settlement.objects.create(
            trip=self.trip,
            payer=self.other_member,
            payee=self.member_to_delete,
            amount=Decimal("500.00"),
            note="Paid back",
        )

        response = self.client.post(
            reverse("delete_member", args=[self.trip.id, self.member_to_delete.id])
        )

        self.assertRedirects(response, reverse("expense", args=[self.trip.id]))
        self.assertFalse(Member.objects.filter(id=self.member_to_delete.id).exists())
        self.assertTrue(Member.objects.filter(id=self.other_member.id).exists())
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())
        self.assertEqual(Settlement.objects.count(), 0)

    def test_delete_member_requires_post(self):
        response = self.client.get(
            reverse("delete_member", args=[self.trip.id, self.member_to_delete.id])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Member.objects.filter(id=self.member_to_delete.id).exists())


class HistoryPersistenceTests(PlannerTestCase):
    def setUp(self):
        self.user = self.login_user()

    @patch("planner.views.get_place_info", return_value=("https://example.com/goa.jpg", "A beach destination"))
    def test_trip_search_is_saved_to_database_for_logged_in_user(self, mocked_get_place_info):
        response = self.client.post(reverse("trip"), {"place_name": "goa"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SearchHistory.objects.count(), 1)

        history = SearchHistory.objects.get()
        self.assertEqual(history.owner, self.user)
        self.assertEqual(history.place, "Goa")
        self.assertEqual(history.raw_query, "goa")
        self.assertEqual(history.image, "https://example.com/goa.jpg")
        self.assertEqual(history.desc, "A beach destination")

    @patch("planner.views._get_wikipedia_images", return_value=[])
    @patch("planner.views.get_place_info", return_value=("https://example.com/goa.jpg", "A beach destination"))
    def test_budget_calculation_is_saved_to_database_for_logged_in_user(self, mocked_get_place_info, mocked_images):
        response = self.client.post(
            f"{reverse('create_trip')}?place=Goa",
            {
                "people": 4,
                "days": 3,
                "hotel_per_night": 2000,
                "food_per_day": 500,
                "travel": 3000,
                "activities": 1000,
                "misc": 500,
                "contingency_pct": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BudgetHistory.objects.count(), 1)

        history = BudgetHistory.objects.get()
        self.assertEqual(history.owner, self.user)
        self.assertEqual(history.place, "Goa")
        self.assertEqual(history.people, 4)
        self.assertEqual(history.days, 3)
        self.assertEqual(history.total, Decimal("18150.00"))
        self.assertEqual(history.per_person, Decimal("4537.50"))
        self.assertEqual(history.base_total, Decimal("16500.00"))
        self.assertEqual(history.contingency, Decimal("1650.00"))

    def test_home_reads_only_logged_in_users_latest_history(self):
        other_user = self.create_user(username="other")

        SearchHistory.objects.create(
            owner=self.user,
            place="Munnar",
            raw_query="munnar",
            image="https://example.com/munnar.jpg",
            desc="Hill station",
        )
        SearchHistory.objects.create(
            owner=other_user,
            place="Goa",
            raw_query="goa",
            image="https://example.com/goa.jpg",
            desc="Beach",
        )

        BudgetHistory.objects.create(
            owner=self.user,
            place="Munnar",
            people=2,
            days=2,
            hotel_per_night=Decimal("2500.00"),
            food_per_day=Decimal("750.00"),
            travel=Decimal("2000.00"),
            activities=Decimal("500.00"),
            misc=Decimal("250.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("5000.00"),
            food_total=Decimal("3000.00"),
            base_total=Decimal("10750.00"),
            contingency=Decimal("1075.00"),
            total=Decimal("11825.00"),
            per_person=Decimal("5912.50"),
        )
        BudgetHistory.objects.create(
            owner=other_user,
            place="Goa",
            people=3,
            days=4,
            hotel_per_night=Decimal("2000.00"),
            food_per_day=Decimal("500.00"),
            travel=Decimal("3000.00"),
            activities=Decimal("1500.00"),
            misc=Decimal("500.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("8000.00"),
            food_total=Decimal("6000.00"),
            base_total=Decimal("19000.00"),
            contingency=Decimal("1900.00"),
            total=Decimal("20900.00"),
            per_person=Decimal("6966.67"),
        )

        trip = Trip.objects.create(owner=self.user, trip_name="Munnar")
        payer = Member.objects.create(trip=trip, name="Rohit")
        Member.objects.create(trip=trip, name="Sudeep")
        Expense.objects.create(
            trip=trip,
            paid_by=payer,
            amount=Decimal("1200.00"),
            description="Cab",
        )

        other_trip = Trip.objects.create(owner=other_user, trip_name="Goa")
        other_payer = Member.objects.create(trip=other_trip, name="Asha")
        Member.objects.create(trip=other_trip, name="Nina")
        Expense.objects.create(
            trip=other_trip,
            paid_by=other_payer,
            amount=Decimal("5000.00"),
            description="Resort",
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["last_search"].place, "Munnar")
        self.assertEqual(response.context["last_budget"].place, "Munnar")
        self.assertEqual(response.context["last_expense"]["trip_id"], trip.id)
        self.assertEqual(response.context["last_expense"]["total"], Decimal("1200.00"))
        self.assertEqual(response.context["last_expense"]["per_person"], Decimal("600.00"))


class HistoryPageTests(PlannerTestCase):
    def setUp(self):
        self.user = self.login_user()

    def test_history_page_shows_only_current_users_records(self):
        other_user = self.create_user(username="other")

        SearchHistory.objects.create(
            owner=self.user,
            place="Goa",
            raw_query="goa",
            image="https://example.com/goa.jpg",
            desc="Beach trip",
        )
        SearchHistory.objects.create(
            owner=other_user,
            place="Ooty",
            raw_query="ooty",
            image="https://example.com/ooty.jpg",
            desc="Hill trip",
        )

        BudgetHistory.objects.create(
            owner=self.user,
            place="Goa",
            people=3,
            days=4,
            hotel_per_night=Decimal("2000.00"),
            food_per_day=Decimal("500.00"),
            travel=Decimal("3000.00"),
            activities=Decimal("1500.00"),
            misc=Decimal("500.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("8000.00"),
            food_total=Decimal("6000.00"),
            base_total=Decimal("19000.00"),
            contingency=Decimal("1900.00"),
            total=Decimal("20900.00"),
            per_person=Decimal("6966.67"),
        )
        BudgetHistory.objects.create(
            owner=other_user,
            place="Ooty",
            people=2,
            days=2,
            hotel_per_night=Decimal("1500.00"),
            food_per_day=Decimal("400.00"),
            travel=Decimal("2000.00"),
            activities=Decimal("600.00"),
            misc=Decimal("300.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("3000.00"),
            food_total=Decimal("1600.00"),
            base_total=Decimal("7500.00"),
            contingency=Decimal("750.00"),
            total=Decimal("8250.00"),
            per_person=Decimal("4125.00"),
        )

        trip = Trip.objects.create(owner=self.user, trip_name="Goa Friends")
        payer = Member.objects.create(trip=trip, name="Rohit")
        friend = Member.objects.create(trip=trip, name="Sudeep")
        expense = Expense.objects.create(
            trip=trip,
            paid_by=payer,
            amount=Decimal("1200.00"),
            description="Dinner",
        )
        expense.members_involved.add(payer, friend)
        Settlement.objects.create(
            trip=trip,
            payer=friend,
            payee=payer,
            amount=Decimal("600.00"),
            note="Paid back dinner",
        )

        other_trip = Trip.objects.create(owner=other_user, trip_name="Ooty Riders")
        other_payer = Member.objects.create(trip=other_trip, name="Asha")
        other_friend = Member.objects.create(trip=other_trip, name="Nina")
        other_expense = Expense.objects.create(
            trip=other_trip,
            paid_by=other_payer,
            amount=Decimal("800.00"),
            description="Taxi",
        )
        other_expense.members_involved.add(other_payer, other_friend)

        response = self.client.get(reverse("history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{self.user.username}'s saved history")
        self.assertContains(response, "Goa")
        self.assertContains(response, "Goa Friends")
        self.assertNotContains(response, "Ooty")
        self.assertNotContains(response, "Ooty Riders")
        self.assertEqual(response.context["history_counts"]["searches"], 1)
        self.assertEqual(response.context["history_counts"]["budgets"], 1)
        self.assertEqual(response.context["history_counts"]["trips"], 1)
        self.assertEqual(response.context["history_counts"]["expense_entries"], 1)
        self.assertEqual(response.context["history_counts"]["settlement_entries"], 1)


class OwnershipAccessTests(PlannerTestCase):
    def setUp(self):
        self.user = self.login_user()
        self.other_user = self.create_user(username="other")

    def test_user_cannot_open_another_users_trip(self):
        trip = Trip.objects.create(owner=self.other_user, trip_name="Hidden Trip")

        response = self.client.get(reverse("expense", args=[trip.id]))

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_another_users_search_history(self):
        history = SearchHistory.objects.create(
            owner=self.other_user,
            place="Goa",
            raw_query="goa",
            image="https://example.com/goa.jpg",
            desc="Beach trip",
        )

        response = self.client.post(reverse("delete_search_history", args=[history.id]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SearchHistory.objects.filter(id=history.id).exists())

    def test_delete_expense_requires_post(self):
        trip = Trip.objects.create(owner=self.user, trip_name="Goa")
        payer = Member.objects.create(trip=trip, name="Rohit")
        expense = Expense.objects.create(
            trip=trip,
            paid_by=payer,
            amount=Decimal("1200.00"),
            description="Dinner",
        )

        response = self.client.get(reverse("delete_expense", args=[trip.id, expense.id]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Expense.objects.filter(id=expense.id).exists())


class HistoryDeleteViewTests(PlannerTestCase):
    def setUp(self):
        self.user = self.login_user()
        self.other_user = self.create_user(username="other")

    def test_delete_budget_history_entry(self):
        budget = BudgetHistory.objects.create(
            owner=self.user,
            place="Goa",
            people=2,
            days=3,
            hotel_per_night=Decimal("2000.00"),
            food_per_day=Decimal("500.00"),
            travel=Decimal("3000.00"),
            activities=Decimal("1000.00"),
            misc=Decimal("500.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("6000.00"),
            food_total=Decimal("3000.00"),
            base_total=Decimal("13500.00"),
            contingency=Decimal("1350.00"),
            total=Decimal("14850.00"),
            per_person=Decimal("7425.00"),
        )

        response = self.client.post(reverse("delete_budget_history", args=[budget.id]))

        self.assertRedirects(response, reverse("history"))
        self.assertFalse(BudgetHistory.objects.filter(id=budget.id).exists())

    def test_delete_trip_history_entry_cascades_related_records(self):
        trip = Trip.objects.create(owner=self.user, trip_name="Friends Goa")
        payer = Member.objects.create(trip=trip, name="Rohit")
        payee = Member.objects.create(trip=trip, name="Sudeep")
        expense = Expense.objects.create(
            trip=trip,
            paid_by=payer,
            amount=Decimal("1200.00"),
            description="Dinner",
        )
        expense.members_involved.add(payer, payee)
        settlement = Settlement.objects.create(
            trip=trip,
            payer=payee,
            payee=payer,
            amount=Decimal("600.00"),
            note="Paid back dinner",
        )

        response = self.client.post(reverse("delete_trip_history", args=[trip.id]))

        self.assertRedirects(response, reverse("history"))
        self.assertFalse(Trip.objects.filter(id=trip.id).exists())
        self.assertFalse(Member.objects.filter(id__in=[payer.id, payee.id]).exists())
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())
        self.assertFalse(Settlement.objects.filter(id=settlement.id).exists())

    def test_clear_history_sections_only_remove_current_users_records(self):
        SearchHistory.objects.create(
            owner=self.user,
            place="Goa",
            raw_query="goa",
            image="https://example.com/goa.jpg",
            desc="Beach trip",
        )
        SearchHistory.objects.create(
            owner=self.other_user,
            place="Ooty",
            raw_query="ooty",
            image="https://example.com/ooty.jpg",
            desc="Hill trip",
        )

        BudgetHistory.objects.create(
            owner=self.user,
            place="Goa",
            people=2,
            days=3,
            hotel_per_night=Decimal("2000.00"),
            food_per_day=Decimal("500.00"),
            travel=Decimal("3000.00"),
            activities=Decimal("1000.00"),
            misc=Decimal("500.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("6000.00"),
            food_total=Decimal("3000.00"),
            base_total=Decimal("13500.00"),
            contingency=Decimal("1350.00"),
            total=Decimal("14850.00"),
            per_person=Decimal("7425.00"),
        )
        BudgetHistory.objects.create(
            owner=self.other_user,
            place="Ooty",
            people=2,
            days=2,
            hotel_per_night=Decimal("1500.00"),
            food_per_day=Decimal("400.00"),
            travel=Decimal("2000.00"),
            activities=Decimal("600.00"),
            misc=Decimal("300.00"),
            contingency_pct=Decimal("10.00"),
            hotel_total=Decimal("3000.00"),
            food_total=Decimal("1600.00"),
            base_total=Decimal("7500.00"),
            contingency=Decimal("750.00"),
            total=Decimal("8250.00"),
            per_person=Decimal("4125.00"),
        )

        trip = Trip.objects.create(owner=self.user, trip_name="Goa")
        member = Member.objects.create(trip=trip, name="Rohit")
        Expense.objects.create(
            trip=trip,
            paid_by=member,
            amount=Decimal("1200.00"),
            description="Dinner",
        )

        other_trip = Trip.objects.create(owner=self.other_user, trip_name="Ooty")
        other_member = Member.objects.create(trip=other_trip, name="Asha")
        Expense.objects.create(
            trip=other_trip,
            paid_by=other_member,
            amount=Decimal("900.00"),
            description="Taxi",
        )

        self.client.post(reverse("clear_search_history"))
        self.client.post(reverse("clear_budget_history"))
        response = self.client.post(reverse("clear_trip_history"))

        self.assertRedirects(response, reverse("history"))
        self.assertEqual(SearchHistory.objects.filter(owner=self.user).count(), 0)
        self.assertEqual(BudgetHistory.objects.filter(owner=self.user).count(), 0)
        self.assertEqual(Trip.objects.filter(owner=self.user).count(), 0)
        self.assertEqual(SearchHistory.objects.filter(owner=self.other_user).count(), 1)
        self.assertEqual(BudgetHistory.objects.filter(owner=self.other_user).count(), 1)
        self.assertEqual(Trip.objects.filter(owner=self.other_user).count(), 1)
