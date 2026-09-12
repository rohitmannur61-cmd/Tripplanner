from __future__ import annotations

import base64
import io
import json
from decimal import Decimal
from typing import Iterable
from urllib.parse import quote, quote_plus

import requests
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    LoginForm,
    RegisterForm,
)
from .models import (
    BudgetHistory,
    Expense,
    Member,
    SearchHistory,
    Settlement,
    Trip,
)
from .recommender import RECOMMENDER


def _get_base64_svg(text):
    safe_text = quote(text)
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='800' height='450'><rect width='100%' height='100%' fill='#1a6f7a'/><text x='50%' y='50%' text-anchor='middle' dominant-baseline='middle' font-family='Arial, sans-serif' font-size='48' fill='white'>{safe_text}</text></svg>"
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

FALLBACK_IMAGE = _get_base64_svg("No Image Found")


def _to_stored_decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _get_safe_redirect(request: HttpRequest, redirect_to: str | None) -> str:
    if redirect_to and url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect_to
    return reverse("home")


def _get_latest_expense_summary(user):
    latest_expense = (
        Expense.objects.select_related("trip")
        .filter(trip__owner=user)
        .order_by("-created_at", "-id")
        .first()
    )
    latest_settlement = (
        Settlement.objects.select_related("trip")
        .filter(trip__owner=user)
        .order_by("-created_at", "-id")
        .first()
    )

    if latest_expense and latest_settlement:
        expense_marker = (latest_expense.created_at, latest_expense.id)
        settlement_marker = (latest_settlement.created_at, latest_settlement.id)
        trip_obj = latest_expense.trip if expense_marker >= settlement_marker else latest_settlement.trip
    elif latest_expense is not None:
        trip_obj = latest_expense.trip
    elif latest_settlement is not None:
        trip_obj = latest_settlement.trip
    else:
        return None

    members_count = Member.objects.filter(trip=trip_obj).count()
    expense_records = list(Expense.objects.filter(trip=trip_obj).only("amount"))
    total = sum((expense.amount for expense in expense_records), Decimal("0.00"))
    per_person = (total / Decimal(members_count)) if members_count else Decimal("0.00")

    return {
        "trip_id": trip_obj.id,
        "trip_name": trip_obj.trip_name,
        "total": total,
        "per_person": per_person.quantize(Decimal("0.01")),
        "members": members_count,
        "expenses": len(expense_records),
    }


def _fetch_wikipedia_summary(title: str, headers: dict[str, str]) -> tuple[str | None, str, bool]:
    formatted_title = title.strip().replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_title}"
    resp = requests.get(url, headers=headers, timeout=5)
    data = resp.json() if resp.status_code == 200 else {}

    image = (
        data.get("originalimage", {}).get("source")
        or data.get("thumbnail", {}).get("source")
    )
    desc = data.get("extract", "No description found.")
    is_disambig = data.get("type") == "disambiguation" or "may refer to" in desc.lower()
    return image, desc, is_disambig


def _search_wikipedia_titles(place: str, headers: dict[str, str], limit: int = 5) -> list[str]:
    search = place.strip()
    if not search:
        return []

    mw_api = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": search,
        "srlimit": limit,
        "format": "json",
    }
    try:
        resp = requests.get(mw_api, params=params, headers=headers, timeout=5)
        data = resp.json() if resp.status_code == 200 else {}
        results = (data.get("query") or {}).get("search") or []
        return [r.get("title") for r in results if r.get("title")]
    except Exception:
        return []


def get_place_info(place: str | None):
    if not place:
        return "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=1600", "No description."

    headers = {"User-Agent": "TripPlannerApp/1.0"}
    title = place.strip()

    try:
        image, desc, is_disambig = _fetch_wikipedia_summary(title, headers)
        if is_disambig or not image:
            candidates = _search_wikipedia_titles(title, headers, limit=5)
            fallback = None
            for candidate in candidates:
                if candidate.lower() == title.lower():
                    continue
                image2, desc2, is_disambig2 = _fetch_wikipedia_summary(candidate, headers)
                if is_disambig2:
                    continue
                if image2:
                    image, desc, title = image2, desc2, candidate
                    break
                if fallback is None:
                    fallback = (image2, desc2, candidate)
            if image is None and fallback is not None:
                image, desc, title = fallback
        if not image:
            image = "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=1600"

        # Try to fetch a longer intro (more detailed than the REST summary).
        try:
            mw_api = "https://en.wikipedia.org/w/api.php"
            mw_params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "exsectionformat": "plain",
                "redirects": 1,
                "titles": title,
                "exchars": 1600,
            }
            mw_resp = requests.get(mw_api, params=mw_params, headers=headers, timeout=5)
            mw_data = mw_resp.json() or {}
            pages = (mw_data.get("query") or {}).get("pages") or {}
            page = next(iter(pages.values()), {}) if isinstance(pages, dict) else {}
            long_extract = (page or {}).get("extract") or ""
            long_extract = " ".join(long_extract.split())
            if len(long_extract) >= 250:
                desc = long_extract
        except Exception:
            pass

        return image, desc
    except Exception:
        return "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=1600", "Error loading data."


def _get_wikipedia_images(place: str, limit: int = 8) -> list[str]:
    """
    Try to fetch multiple real images for the place from Wikipedia's REST API.
    Returns a list of absolute image URLs (best effort).
    """
    headers = {"User-Agent": "TripPlannerApp/1.0"}
    candidates = [place] + _search_wikipedia_titles(place, headers, limit=5)

    for candidate in candidates:
        if not candidate:
            continue
        formatted_place = candidate.strip().replace(" ", "_")
        url = f"https://en.wikipedia.org/api/rest_v1/page/media-list/{formatted_place}"

        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                continue
            data = resp.json() or {}
            items = (data.get("items") or [])[:200]

            images: list[str] = []
            for item in items:
                if item.get("type") != "image":
                    continue
                srcset = item.get("srcset") or []
                if isinstance(srcset, list) and srcset:
                    # pick the largest entry available
                    best = srcset[-1].get("src") or srcset[0].get("src")
                    if best:
                        images.append(best)
                else:
                    # fallback key occasionally present
                    original = (item.get("original") or {}).get("source")
                    if original:
                        images.append(original)

                if len(images) >= limit:
                    break

            # De-dupe while keeping order
            seen: set[str] = set()
            out: list[str] = []
            for u in images:
                if u and u not in seen:
                    seen.add(u)
                    out.append(u)
            if out:
                return out
        except Exception:
            continue

    return []


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("home")
    else:
        form = RegisterForm()

    return render(request, "register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    redirect_to = request.POST.get("next") or request.GET.get("next")
    form = LoginForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        return redirect(_get_safe_redirect(request, redirect_to))

    return render(
        request,
        "planner_auth/login.html",
        {
            "form": form,
            "next": redirect_to or "",
        },
    )


def home(request):
    summary = {
        "last_search": None,
        "last_budget": None,
        "last_expense": None,
    }

    if request.user.is_authenticated:
        summary = {
            "last_search": SearchHistory.objects.filter(owner=request.user).first()
            or request.session.get("last_search"),
            "last_budget": BudgetHistory.objects.filter(owner=request.user).first()
            or request.session.get("last_budget"),
            "last_expense": _get_latest_expense_summary(request.user)
            or request.session.get("last_expense"),
        }

    # Add platform-wide stats — real-time from database
    total_tracked_raw = float(Expense.objects.aggregate(Sum('amount'))['amount__sum'] or 0)
    summary.update({
        "all_trips_count": Trip.objects.count(),
        "all_destinations_count": SearchHistory.objects.values('place').distinct().count(),
        "total_amount_tracked": total_tracked_raw,
    })

    return render(request, "home.html", summary)


def logout_view(request):
    auth_logout(request)
    return redirect("home")


@login_required
def history(request):
    searches = list(SearchHistory.objects.filter(owner=request.user))
    budgets = list(BudgetHistory.objects.filter(owner=request.user))

    trips = (
        Trip.objects.filter(owner=request.user)
        .order_by("-id")
        .prefetch_related(
            Prefetch("member_set", queryset=Member.objects.order_by("id")),
            Prefetch(
                "expense_set",
                queryset=Expense.objects.select_related("paid_by")
                .prefetch_related("members_involved")
                .order_by("-created_at", "-id"),
            ),
            Prefetch(
                "settlements",
                queryset=Settlement.objects.select_related("payer", "payee").order_by(
                    "-created_at", "-id"
                ),
            ),
        )
    )

    trip_history: list[dict[str, object]] = []
    expense_entry_count = 0
    settlement_entry_count = 0

    for trip_obj in trips:
        members = list(trip_obj.member_set.all())
        expenses = list(trip_obj.expense_set.all())
        settlements = list(trip_obj.settlements.all())
        total_amount = sum((expense.amount for expense in expenses), Decimal("0.00"))

        expense_entry_count += len(expenses)
        settlement_entry_count += len(settlements)

        trip_history.append(
            {
                "trip": trip_obj,
                "members": members,
                "expenses": expenses,
                "settlements": settlements,
                "member_count": len(members),
                "expense_count": len(expenses),
                "settlement_count": len(settlements),
                "total_amount": total_amount.quantize(Decimal("0.01")),
            }
        )

    history_counts = {
        "searches": len(searches),
        "budgets": len(budgets),
        "trips": len(trip_history),
        "expense_entries": expense_entry_count,
        "settlement_entries": settlement_entry_count,
    }

    return render(
        request,
        "history.html",
        {
            "searches": searches,
            "budgets": budgets,
            "trip_history": trip_history,
            "history_counts": history_counts,
        },
    )


@login_required
@require_POST
def delete_search_history(request, history_id: int):
    history_obj = get_object_or_404(SearchHistory, id=history_id, owner=request.user)
    history_obj.delete()
    return redirect("history")


@login_required
@require_POST
def delete_budget_history(request, history_id: int):
    history_obj = get_object_or_404(BudgetHistory, id=history_id, owner=request.user)
    history_obj.delete()
    return redirect("history")


@login_required
@require_POST
def delete_trip_history(request, trip_id: int):
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    trip_obj.delete()
    return redirect("history")


@login_required
@require_POST
def clear_search_history(request):
    SearchHistory.objects.filter(owner=request.user).delete()
    return redirect("history")


@login_required
@require_POST
def clear_budget_history(request):
    BudgetHistory.objects.filter(owner=request.user).delete()
    return redirect("history")


@login_required
@require_POST
def clear_trip_history(request):
    Trip.objects.filter(owner=request.user).delete()
    return redirect("history")


@login_required
def trip(request):
    places = []
    recommendations = []
    category_results = []
    active_category = ""

    # ── Category browsing (GET param) ──
    active_category = (request.GET.get("category") or "").strip()

    if request.method == "POST":
        place_name = (request.POST.get("place_name") or "").strip()
        if place_name:
            request.session["last_search"] = {
                "place": place_name.title(),
                "raw": place_name,
            }
            image, desc = get_place_info(place_name)
            if not image:
                image = f"https://picsum.photos/id/{abs(hash(place_name)) % 1000}/800/600"

            SearchHistory.objects.create(
                owner=request.user,
                place=place_name.title(),
                raw_query=place_name,
                image=image,
                desc=desc,
            )
            places.append(
                {
                    "name": place_name.title(),
                    "image": image,
                    "desc": desc,
                    "budget": "₹3,000 – ₹10,000",
                    "rating": 4.5,
                }
            )

            # Get recommendations from the hybrid ML engine
            recommendations = RECOMMENDER.get_recommendations(place_name, top_n=6)

    if not recommendations:
        # Default recommendations when no search is performed
        recommendations = RECOMMENDER.get_recommendations("nature", top_n=6)

    # ── Category filter results ──
    if active_category:
        category_results = RECOMMENDER.get_by_category(active_category, limit=9)

    # ── All available categories for the pill bar ──
    all_categories = RECOMMENDER.get_all_categories()

    # ── Resolve images server-side (Wikipedia → Picsum ID fallback) ──
    headers = {"User-Agent": "TripPlanner/1.0 (educational-project)"}
    for rec_list in [recommendations, category_results]:
        for rec in rec_list:
            if "image_url" in rec:
                continue
            try:
                wiki_img, _, _ = _fetch_wikipedia_summary(rec["place_name"], headers)
                if wiki_img:
                    rec["image_url"] = wiki_img
                    continue
            except Exception:
                pass
            # Deterministic Picsum ID — no redirects, bypasses ORB
            safe_id = abs(hash(rec["place_name"])) % 1000
            rec["image_url"] = f"https://picsum.photos/id/{safe_id}/600/400"

    return render(request, "trip.html", {
        "places": places,
        "recommendations": recommendations,
        "category_results": category_results,
        "active_category": active_category,
        "all_categories": all_categories,
        "fallback_image": FALLBACK_IMAGE,
    })


@login_required
def create_trip(request):
    place = request.GET.get("place")

    image = "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=1600"
    desc = ""
    if place:
        image, desc = get_place_info(place)

    query = (place or "").strip() or "travel"
    q = quote_plus(query)

    # Always provide a fallback that doesn't depend on external photo APIs.
    fallback_image = FALLBACK_IMAGE

    # The template expects `images` for the slider + hero background (images.0).
    # Prefer real place images from Wikipedia, then fall back to Unsplash random.
    images: list[str] = []
    if place:
        images.extend(_get_wikipedia_images(place, limit=8))
    if image:
        images.insert(0, image)

    # Add multiple photos for the place using stable IDs to avoid redirects and ORB issues.
    hash_seed = abs(hash(q)) % 1000
    images.extend([f"https://picsum.photos/id/{(hash_seed + i) % 1000}/1600/900" for i in range(1, 9)])

    # Ensure there is always at least one valid entry for the hero.
    if not images:
        images = [fallback_image]

    # De-dupe while keeping order.
    seen: set[str] = set()
    deduped: list[str] = []
    for u in images:
        if u and u not in seen:
            seen.add(u)
            deduped.append(u)
    images = deduped

    # Ensure we have at least a few non-cover images for the slider.
    # Slider will intentionally skip images[0] (cover).
    cover = images[0] if images else fallback_image
    while len(images) < 6:
        candidate = f"https://placehold.co/1600x900?text={q}+Photo+{len(images)}"
        if candidate != cover:
            images.append(candidate)

    def _to_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    budget_input = {
        "people": 2,
        "days": 2,
        "hotel_per_night": 0.0,
        "food_per_day": 0.0,
        "travel": 0.0,
        "activities": 0.0,
        "misc": 0.0,
        "contingency_pct": 10.0,
    }

    total = None
    per_person = None
    budget_breakdown = None

    if request.method == "POST":
        budget_input["people"] = max(1, _to_int(request.POST.get("people"), 2))
        budget_input["days"] = max(1, _to_int(request.POST.get("days"), 2))
        budget_input["hotel_per_night"] = max(0.0, _to_float(request.POST.get("hotel_per_night"), 0.0))
        budget_input["food_per_day"] = max(0.0, _to_float(request.POST.get("food_per_day"), 0.0))
        budget_input["travel"] = max(0.0, _to_float(request.POST.get("travel"), 0.0))
        budget_input["activities"] = max(0.0, _to_float(request.POST.get("activities"), 0.0))
        budget_input["misc"] = max(0.0, _to_float(request.POST.get("misc"), 0.0))
        budget_input["contingency_pct"] = max(0.0, _to_float(request.POST.get("contingency_pct"), 10.0))

        hotel_total_legacy = _to_float(request.POST.get("hotel"), 0.0)
        food_total_legacy = _to_float(request.POST.get("food"), 0.0)

        hotel_total = budget_input["hotel_per_night"] * budget_input["days"]
        food_total = budget_input["food_per_day"] * budget_input["people"] * budget_input["days"]
        if hotel_total == 0.0 and hotel_total_legacy > 0.0:
            hotel_total = hotel_total_legacy
        if food_total == 0.0 and food_total_legacy > 0.0:
            food_total = food_total_legacy

        base_total = (
            hotel_total
            + budget_input["travel"]
            + food_total
            + budget_input["activities"]
            + budget_input["misc"]
        )
        contingency = base_total * (budget_input["contingency_pct"] / 100.0)
        total = round(base_total + contingency, 2)
        per_person = round(total / budget_input["people"], 2) if budget_input["people"] else 0.0

        budget_breakdown = {
            "hotel_total": round(hotel_total, 2),
            "food_total": round(food_total, 2),
            "travel": round(budget_input["travel"], 2),
            "activities": round(budget_input["activities"], 2),
            "misc": round(budget_input["misc"], 2),
            "contingency": round(contingency, 2),
            "base_total": round(base_total, 2),
        }

        request.session["last_budget"] = {
            "place": place or "",
            "people": budget_input["people"],
            "days": budget_input["days"],
            "total": total,
            "per_person": per_person,
            "base_total": budget_breakdown["base_total"],
            "contingency": budget_breakdown["contingency"],
        }
        BudgetHistory.objects.create(
            owner=request.user,
            place=place or "",
            cover_image=image,
            description=desc,
            people=budget_input["people"],
            days=budget_input["days"],
            hotel_per_night=_to_stored_decimal(budget_input["hotel_per_night"]),
            food_per_day=_to_stored_decimal(budget_input["food_per_day"]),
            travel=_to_stored_decimal(budget_input["travel"]),
            activities=_to_stored_decimal(budget_input["activities"]),
            misc=_to_stored_decimal(budget_input["misc"]),
            contingency_pct=_to_stored_decimal(budget_input["contingency_pct"]),
            hotel_total=_to_stored_decimal(budget_breakdown["hotel_total"]),
            food_total=_to_stored_decimal(budget_breakdown["food_total"]),
            base_total=_to_stored_decimal(budget_breakdown["base_total"]),
            contingency=_to_stored_decimal(budget_breakdown["contingency"]),
            total=_to_stored_decimal(total),
            per_person=_to_stored_decimal(per_person),
        )

    # ── Advanced features ──
    itinerary = []
    dest_details = None
    similar_destinations = []
    if place:
        itinerary = RECOMMENDER.generate_itinerary(place, days=3)
        dest_details = RECOMMENDER.get_destination_details(place)
        similar_destinations = RECOMMENDER.get_recommendations(place, top_n=3)
        # Resolve images for similar destinations
        _headers = {"User-Agent": "TripPlanner/1.0 (educational-project)"}
        for rec in similar_destinations:
            if "image_url" not in rec:
                try:
                    wiki_img, _, _ = _fetch_wikipedia_summary(rec["place_name"], _headers)
                    if wiki_img:
                        rec["image_url"] = wiki_img
                        continue
                except Exception:
                    pass
                rec["image_url"] = f"https://picsum.photos/id/{abs(hash(rec['place_name'])) % 1000}/400/250"

    return render(
        request,
        "create_trip.html",
        {
            "place": place,
            "image": image,
            "images": images,
            "fallback_image": fallback_image,
            "desc": desc,
            "total": total,
            "per_person": per_person,
            "budget_input": budget_input,
            "budget_breakdown": budget_breakdown,
            "itinerary": itinerary,
            "dest_details": dest_details,
            "similar_destinations": similar_destinations,
        },
    )


def _generate_expense_graph(expenses: Iterable[Expense]) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    labels: list[str] = []
    amounts: list[float] = []

    for expense in expenses:
        labels.append(expense.description or "Other")
        amounts.append(float(expense.amount))

    if not labels:
        return None

    plt.figure(figsize=(5, 4))
    plt.bar(labels, amounts)
    plt.title("Expense Distribution")
    plt.xlabel("Category")
    plt.ylabel("Amount")

    buffer = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buffer, format="png")
    buffer.seek(0)

    graph = base64.b64encode(buffer.getvalue()).decode("utf-8")
    buffer.close()
    plt.close()
    return graph


@login_required
def expense_overview(request):
    """
    Redirects to the first trip's expense page, creating a trip if needed.
    """
    # Prefer a trip that already has members/expenses so the page is usable.
    member = (
        Member.objects.select_related("trip")
        .filter(trip__owner=request.user)
        .order_by("-id")
        .first()
    )
    if member is not None:
        trip_obj = member.trip
    else:
        last_expense = (
            Expense.objects.select_related("trip")
            .filter(trip__owner=request.user)
            .order_by("-created_at", "-id")
            .first()
        )
        if last_expense is not None:
            trip_obj = last_expense.trip
        else:
            trip_obj = Trip.objects.filter(owner=request.user).order_by("id").first()
            if trip_obj is None:
                trip_obj = Trip.objects.create(owner=request.user, trip_name="My Trip")
    return redirect("expense", trip_id=trip_obj.id)


@login_required
@transaction.atomic
def expense(request, trip_id: int):
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    members = list(Member.objects.filter(trip=trip_obj).order_by("id"))

    if request.method == "POST":
        form_type = (request.POST.get("form_type") or "expense").strip().lower()

        if form_type == "member":
            raw_names = (request.POST.get("member_name") or "").strip()
            if raw_names:
                names = [n.strip() for n in raw_names.replace("\n", ",").split(",") if n.strip()]
                seen: set[str] = set()
                for name in names:
                    key = name.lower()
                    if key in seen or Member.objects.filter(trip=trip_obj, name__iexact=name).exists():
                        continue
                    seen.add(key)
                    Member.objects.create(trip=trip_obj, name=name)
            return redirect("expense", trip_id=trip_obj.id)

        if form_type == "settlement":
            payer_id = request.POST.get("payer")
            payee_id = request.POST.get("payee")
            amount_raw = (request.POST.get("amount") or "0").strip()
            note = (request.POST.get("note") or "").strip()

            payer = get_object_or_404(Member, id=payer_id, trip=trip_obj)
            payee = get_object_or_404(Member, id=payee_id, trip=trip_obj)

            if payer.id != payee.id:
                try:
                    amount = Decimal(amount_raw)
                    if amount > 0:
                        Settlement.objects.create(
                            trip=trip_obj,
                            payer=payer,
                            payee=payee,
                            amount=amount,
                            note=note,
                        )
                except Exception:
                    pass

            return redirect("expense", trip_id=trip_obj.id)

        # default: expense form
        paid_by_id = request.POST.get("paid_by")
        amount_raw = (request.POST.get("amount") or "0").strip()
        category = request.POST.get("category", "Misc")
        description = (request.POST.get("description") or "").strip()
        involved_ids = request.POST.getlist("members_involved")
        receipt = request.FILES.get("receipt_image")

        if not paid_by_id:
            return redirect("expense", trip_id=trip_obj.id)

        paid_by = get_object_or_404(Member, id=paid_by_id, trip=trip_obj)
        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            expense_obj = Expense.objects.create(
                trip=trip_obj,
                paid_by=paid_by,
                amount=amount,
                category=category,
                description=description,
                receipt_image=receipt,
            )
            if involved_ids:
                involved_members = Member.objects.filter(trip=trip_obj, id__in=involved_ids)
                expense_obj.members_involved.add(*involved_members)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Failed to save expense: %s", exc)

        return redirect("expense", trip_id=trip_obj.id)

    expenses = list(
        Expense.objects.filter(trip=trip_obj)
        .select_related("paid_by")
        .prefetch_related("members_involved")
        .order_by("-created_at", "-id")
    )
    settlement_records = list(
        Settlement.objects.filter(trip=trip_obj)
        .select_related("payer", "payee")
        .order_by("-created_at", "-id")
    )

    total = sum((e.amount) for e in expenses) or Decimal("0.00")
    per_person = (total / Decimal(len(members))) if members else Decimal("0.00")

    balances_by_member: dict[int, Decimal] = {m.id: Decimal("0.00") for m in members}
    all_member_ids = [m.id for m in members]

    for e in expenses:
        balances_by_member[e.paid_by_id] += e.amount

        involved = list(e.members_involved.all())
        involved_ids = [m.id for m in involved] if involved else all_member_ids

        if involved_ids:
            share = e.amount / Decimal(len(involved_ids))
            for mid in involved_ids:
                balances_by_member[mid] -= share

    # Apply recorded settlements (repayments) so balances change over time.
    # payer -> payee reduces payer debt / reduces payee credit.
    for s in settlement_records:
        balances_by_member[s.payer_id] += s.amount
        balances_by_member[s.payee_id] -= s.amount

    net_balances: dict[str, Decimal] = {m.name: balances_by_member.get(m.id, Decimal("0.00")).quantize(Decimal("0.01")) for m in members}

    creditors: list[list[object]] = []
    debtors: list[list[object]] = []
    for mid, bal in balances_by_member.items():
        if bal > 0:
            creditors.append([mid, bal])
        elif bal < 0:
            debtors.append([mid, -bal])

    settlement_suggestions: list[dict] = []
    for debtor_id, debt_amt in debtors:
        remaining = float(debt_amt)
        for creditor in creditors:
            if remaining <= 0:
                break
            creditor_id, credit_amt = creditor
            credit_amt = float(credit_amt)
            if credit_amt <= 0:
                continue
            pay = min(remaining, credit_amt)
            
            debtor_obj = next(m for m in members if m.id == debtor_id)
            creditor_obj = next(m for m in members if m.id == creditor_id)

            settlement_suggestions.append({
                "payer_id": debtor_id,
                "payee_id": creditor_id,
                "payer_name": debtor_obj.name,
                "payee_name": creditor_obj.name,
                "amount": round(pay, 2)
            })
            remaining -= pay
            creditor[1] = round(credit_amt - pay, 2)

    # ── Feature 18: Spend per day (Calendar) ──
    # Convert UTC timestamps to IST (UTC+5:30) for correct local date display
    from datetime import timedelta
    IST_OFFSET = timedelta(hours=5, minutes=30)

    daily_spend = {}
    daily_details: dict[str, list] = {}
    for e in expenses:
        local_dt = e.created_at + IST_OFFSET
        d_str = local_dt.date().isoformat()
        daily_spend[d_str] = daily_spend.get(d_str, Decimal("0.00")) + e.amount
        daily_details.setdefault(d_str, []).append({
            "desc": e.description or "Expense",
            "amount": float(e.amount),
            "category": e.category,
            "paid_by": e.paid_by.name,
        })
    
    calendar_data = [{"date": d, "total": float(s)} for d, s in sorted(daily_spend.items())]
    calendar_detail_data = {d: items for d, items in daily_details.items()}

    # ── Feature 1: Category Distribution (Pie Chart) ──
    actual_by_cat = {cat: Decimal("0.00") for cat, _ in Expense.CATEGORY_CHOICES}
    for e in expenses:
        actual_by_cat[e.category] = actual_by_cat.get(e.category, Decimal("0.00")) + e.amount
    
    category_pie_data = [{"label": k, "value": float(v)} for k, v in actual_by_cat.items() if v > 0]

    # ── Feature 2: Spending Trend ──
    trend_data = [{"date": d, "total": float(s)} for d, s in sorted(daily_spend.items())]

    # ── Feature 5: Daily Average & Stats ──
    trip_days = len(daily_spend) or 1
    daily_avg = total / Decimal(trip_days)
    peak_spend = max(daily_spend.values()) if daily_spend else Decimal("0.00")
    most_expensive_cat = max(actual_by_cat, key=actual_by_cat.get) if total > 0 else "N/A"

    # ── Feature 6: Anomaly Detection (Simple Z-Score) ──
    # If an expense is > 2.5x the mean of its category, flag it
    anomalies = []
    for cat in actual_by_cat:
        cat_expenses = [e for e in expenses if e.category == cat]
        if len(cat_expenses) > 1:
            mean = actual_by_cat[cat] / Decimal(len(cat_expenses))
            for e in cat_expenses:
                if e.amount > (mean * Decimal("2.5")):
                    anomalies.append(e.id)

    # ── Feature 9: Smart Savings Suggestions ──
    suggestions = []
    if actual_by_cat.get("Food", 0) > (total * Decimal("0.4")):
        suggestions.append("🍔 Food is 40%+ of your budget. Consider street food for savings!")
    if actual_by_cat.get("Travel", 0) > (total * Decimal("0.3")):
        suggestions.append("🚕 Transport costs are high. Try walking or local buses.")
    if not suggestions:
        suggestions.append("✅ Your spending is well-balanced. Keep it up!")

    # ── Feature 3: Budget vs Actual ──
    # Try exact match first, then partial (trip name contains place or vice versa), then latest budget
    planned_budget = (
        BudgetHistory.objects.filter(owner=request.user, place__iexact=trip_obj.trip_name).first()
        or BudgetHistory.objects.filter(owner=request.user, place__icontains=trip_obj.trip_name).first()
        or BudgetHistory.objects.filter(owner=request.user, place__in=[
            word for word in trip_obj.trip_name.split() if len(word) > 2
        ]).first()
        or BudgetHistory.objects.filter(owner=request.user).order_by("-id").first()
    )
    comparison = []
    if planned_budget:
        comparison = [
            {"cat": "Hotel", "planned": float(planned_budget.hotel_total or 0), "actual": float(actual_by_cat.get("Hotel", 0))},
            {"cat": "Food", "planned": float(planned_budget.food_total or 0), "actual": float(actual_by_cat.get("Food", 0))},
            {"cat": "Travel", "planned": float(planned_budget.travel or 0), "actual": float(actual_by_cat.get("Travel", 0))},
            {"cat": "Activities", "planned": float(planned_budget.activities or 0), "actual": float(actual_by_cat.get("Activities", 0))},
            {"cat": "Misc", "planned": float(planned_budget.misc or 0), "actual": float(actual_by_cat.get("Misc", 0))},
        ]
        # Only show categories that have either planned or actual spend
        comparison = [c for c in comparison if c["planned"] > 0 or c["actual"] > 0]
    else:
        # No budget plan found — still show actual spending by category
        comparison = [
            {"cat": cat, "planned": 0, "actual": float(actual_by_cat.get(cat, 0))}
            for cat, _ in Expense.CATEGORY_CHOICES
            if actual_by_cat.get(cat, 0) > 0
        ]

    return render(
        request,
        "expense.html",
        {
            "trip": trip_obj,
            "members": members,
            "expenses": expenses,
            "total": total,
            "per_person": per_person,
            "daily_avg": daily_avg.quantize(Decimal("0.01")),
            "peak_spend": peak_spend.quantize(Decimal("0.01")),
            "most_expensive_cat": most_expensive_cat,
            "net_balances": net_balances,
            "settlement_records": settlement_records,
            "settlements": settlement_suggestions,
            "calendar_data": json.dumps(calendar_data),
            "calendar_detail_data": json.dumps(calendar_detail_data),
            "trend_data": json.dumps(trend_data),
            "category_pie_data": json.dumps(category_pie_data),
            "comparison": json.dumps(comparison),
            "anomalies": anomalies,
            "suggestions": suggestions,
            "categories": [c[0] for c in Expense.CATEGORY_CHOICES],
            "all_trips": Trip.objects.filter(owner=request.user).order_by("-id"),
        },

    )

@login_required
def export_expenses(request, trip_id: int):
    import csv
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    expenses = (
        Expense.objects.filter(trip=trip_obj)
        .select_related("paid_by")
        .prefetch_related("members_involved")
        .order_by("-created_at", "-id")
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{trip_obj.trip_name}_expenses.csv"'

    # Write UTF-8 BOM so Excel recognises the encoding correctly
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Date', 'Description', 'Category', 'Paid By', 'Amount', 'Split With'])

    for e in expenses:
        involved = e.members_involved.all()
        split_names = ', '.join(m.name for m in involved) if involved else 'Everyone'
        writer.writerow([
            e.created_at.strftime('%Y-%m-%d'),
            e.description,
            e.category,
            e.paid_by.name,
            float(e.amount),
            split_names,
        ])

    return response


@login_required
@require_POST
def delete_expense(request, trip_id: int, expense_id: int):
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    expense_obj = get_object_or_404(Expense, id=expense_id, trip=trip_obj)
    expense_obj.delete()
    return redirect("expense", trip_id=trip_obj.id)


@login_required
@require_POST
def delete_member(request, trip_id: int, member_id: int):
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    member_obj = get_object_or_404(Member, id=member_id, trip=trip_obj)
    member_obj.delete()
    return redirect("expense", trip_id=trip_obj.id)


@login_required
@require_POST
def delete_settlement(request, trip_id: int, settlement_id: int):
    trip_obj = get_object_or_404(Trip, id=trip_id, owner=request.user)
    settlement_obj = get_object_or_404(Settlement, id=settlement_id, trip=trip_obj)
    settlement_obj.delete()
    return redirect("expense", trip_id=trip_obj.id)


@login_required
def hotel_prices_api(request):
    import os
    import requests
    from django.http import JsonResponse
    from datetime import datetime, timedelta
    
    city = request.GET.get("place", "")
    api_key = os.environ.get("MAKCORPS_API_KEY", "")

    if not city:
        return JsonResponse({"error": "No place provided"}, status=400)

    # If the user hasn't provided a valid API key, return mock data designed in the format of Makcorps
    if not api_key or api_key == "your_makcorps_api_key_here":
        return JsonResponse({
            "status": "mock",
            "message": "Using mock data. Please set MAKCORPS_API_KEY in .env for real results.",
            "data": [
                {
                    "name": f"Grand Plaza {city}",
                    "reviews": {"rating": 4.9, "count": 2101},
                    "vendor1": "Booking.com",
                    "price1": "₹ 18,500",
                    "vendor2": "Expedia",
                    "price2": "₹ 19,000"
                },
                {
                    "name": f"The {city} Oasis Resort",
                    "reviews": {"rating": 4.7, "count": 1450},
                    "vendor1": "Hotels.com",
                    "price1": "₹ 14,200",
                    "vendor2": "Agoda",
                    "price2": "₹ 14,000"
                },
                {
                    "name": f"{city} Downtown Suites",
                    "reviews": {"rating": 4.5, "count": 890},
                    "vendor1": "Expedia",
                    "price1": "₹ 9,500",
                    "vendor2": "Hotels.com",
                    "price2": "₹ 9,600"
                },
                {
                    "name": "Boutique Art Hotel",
                    "reviews": {"rating": 4.6, "count": 620},
                    "vendor1": "Booking.com",
                    "price1": "₹ 8,900"
                },
                {
                    "name": "City View Inn",
                    "reviews": {"rating": 4.2, "count": 1105},
                    "vendor1": "Agoda",
                    "price1": "₹ 6,400",
                    "vendor2": "Priceline",
                    "price2": "₹ 6,300"
                },
                {
                    "name": "The Modern Loft",
                    "reviews": {"rating": 4.3, "count": 450},
                    "vendor1": "Booking.com",
                    "price1": "₹ 7,100"
                },
                {
                    "name": f"Sunrise BnB {city}",
                    "reviews": {"rating": 4.8, "count": 230},
                    "vendor1": "Expedia",
                    "price1": "₹ 4,800"
                },
                {
                    "name": "Budget Express",
                    "reviews": {"rating": 3.7, "count": 840},
                    "vendor1": "Booking.com",
                    "price1": "₹ 2,900",
                    "vendor2": "Agoda",
                    "price2": "₹ 2,750"
                },
                {
                    "name": "Backpackers Hostel",
                    "reviews": {"rating": 4.1, "count": 1890},
                    "vendor1": "Hostelworld",
                    "price1": "₹ 1,200"
                }
            ]
        })

    # Real implementation using Makcorps
    # 1. First, we need to map the city to a cityid using mapping API
    # As per docs, Mapping API fetch: https://api.makcorps.com/mapping?term=CityName
    try:
        mapping_url = "https://api.makcorps.com/mapping"
        map_resp = requests.get(mapping_url, params={"term": city})
        map_data = map_resp.json()
        city_id = None
        for item in map_data:
            # try to find the actual cityid
            if item.get("document_id"):
                city_id = item["document_id"]
                break
        
        if not city_id and map_data:
            # fallback if mapping structure is slightly different
            city_id = map_data[0].get("cityid") or map_data[0].get("id") or map_data[0].get("document_id")

        if not city_id:
            return JsonResponse({"error": "City not found in Makcorps database."}, status=404)

        # 2. Call the hotel api with the cityid
        hotel_url = "https://api.makcorps.com/city"
        checkin_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        checkout_date = (datetime.now() + timedelta(days=9)).strftime("%Y-%m-%d")

        params = {
            'cityid': city_id,
            'pagination': '0',
            'cur': 'INR',
            'rooms': '1',
            'adults': '2',
            'checkin': checkin_date,
            'checkout': checkout_date,
            'api_key': api_key
        }

        hotel_resp = requests.get(hotel_url, params=params)
        if hotel_resp.status_code == 200:
            return JsonResponse({
                "status": "success",
                "data": hotel_resp.json()
            })
        else:
            return JsonResponse({"error": f"Makcorps API error: {hotel_resp.text}"}, status=hotel_resp.status_code)
    except Exception as str_exc:
        return JsonResponse({"error": str(str_exc)}, status=500)
