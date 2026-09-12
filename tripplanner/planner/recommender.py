"""
Intelligent Travel Recommendation Engine
=========================================
Hybrid ML system combining:
  1. TF-IDF content-based similarity (description + category + tags)
  2. Haversine geographic proximity scoring
  3. Popularity-weighted ranking (normalized ratings)
  4. Category-interest matching for contextual reasons

Uses scikit-learn for vectorization + cosine similarity, pandas for
data handling, and numpy for fast math.  Designed to be imported as a
singleton and called from Django views.
"""

import os
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Weights for the hybrid scoring formula
# ---------------------------------------------------------------------------
W_SIMILARITY = 0.60   # TF-IDF cosine similarity
W_POPULARITY = 0.20   # Normalized rating (0-1)
W_PROXIMITY  = 0.15   # Geographic closeness bonus
W_CATEGORY   = 0.05   # Category overlap bonus

PROXIMITY_THRESHOLD_KM = 500  # Max distance for proximity bonus


class TravelRecommender:
    """Production-level hybrid travel recommendation engine."""

    def __init__(self, data_path: str) -> None:
        self.df = pd.read_csv(data_path)
        self._prepare_features()

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------
    def _prepare_features(self) -> None:
        """Build TF-IDF matrix over a rich combined-text column."""
        self.df["_text"] = (
            self.df["description"].fillna("")
            + " " + self.df["category"].fillna("")
            + " " + self.df["tags"].fillna("")
            + " " + self.df["state"].fillna("")
            + " " + self.df["attractions"].fillna("")
        ).str.lower()

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),          # unigrams + bigrams
            sublinear_tf=True,           # dampened term-frequency
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.df["_text"])

        # Pre-compute normalized ratings (0-1 scale)
        self.norm_ratings = (self.df["rating"] / 5.0).values

        # Pre-compute category sets for fast overlap scoring
        self.category_sets = [
            set(c.lower().strip() for c in str(cats).split(","))
            for cats in self.df["category"]
        ]

    # ------------------------------------------------------------------
    # Utility: Haversine distance
    # ------------------------------------------------------------------
    @staticmethod
    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return distance in km between two lat/lon points."""
        R = 6_371  # Earth radius km
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2))
            * np.sin(dlon / 2) ** 2
        )
        return float(2 * R * np.arcsin(np.sqrt(a)))

    # ------------------------------------------------------------------
    # Category overlap score
    # ------------------------------------------------------------------
    def _category_overlap(self, idx: int, other_idx: int) -> float:
        a, b = self.category_sets[idx], self.category_sets[other_idx]
        if not a or not b:
            return 0.0
        return len(a & b) / max(len(a | b), 1)

    # ------------------------------------------------------------------
    # Main recommendation method
    # ------------------------------------------------------------------
    def get_recommendations(self, place_name: str, top_n: int = 6) -> list[dict]:
        place_name = place_name.strip().lower()

        # --- Resolve query to a dataset index ---
        match = self.df[self.df["place_name"].str.lower() == place_name]
        if match.empty:
            # Fuzzy fallback: vectorize the raw query text
            input_vec = self.vectorizer.transform([place_name])
            sim_scores = cosine_similarity(input_vec, self.tfidf_matrix).flatten()
            query_idx = None
        else:
            query_idx = int(match.index[0])
            sim_scores = cosine_similarity(
                self.tfidf_matrix[query_idx], self.tfidf_matrix
            ).flatten()

        n = len(self.df)
        final_scores = np.zeros(n)

        # 1. Content similarity
        final_scores += sim_scores * W_SIMILARITY

        # 2. Popularity boost
        final_scores += self.norm_ratings * W_POPULARITY

        # 3 & 4. Proximity + Category (require a known query index)
        reasons: list[str] = ["Recommended for you"] * n
        if query_idx is not None:
            q_lat = float(self.df.loc[query_idx, "latitude"])
            q_lon = float(self.df.loc[query_idx, "longitude"])
            q_name = str(self.df.loc[query_idx, "place_name"])
            q_cats = self.category_sets[query_idx]

            for i in range(n):
                if i == query_idx:
                    continue

                # Proximity bonus
                dist = self.haversine(
                    q_lat, q_lon,
                    float(self.df.loc[i, "latitude"]),
                    float(self.df.loc[i, "longitude"]),
                )
                if dist < PROXIMITY_THRESHOLD_KM:
                    prox_bonus = 1.0 - (dist / PROXIMITY_THRESHOLD_KM)
                    final_scores[i] += prox_bonus * W_PROXIMITY

                # Category overlap bonus
                cat_score = self._category_overlap(query_idx, i)
                final_scores[i] += cat_score * W_CATEGORY

                # Build human-readable reason
                overlap = q_cats & self.category_sets[i]
                if dist < 300:
                    reasons[i] = f"Near {q_name}"
                elif overlap:
                    shared = ", ".join(sorted(overlap)).title()
                    reasons[i] = f"Matches your interest in {shared.split(',')[0].strip()}"
                elif sim_scores[i] > 0.25:
                    reasons[i] = f"Similar to {q_name}"
        else:
            # No exact match — use tag-style reasons
            for i in range(n):
                if sim_scores[i] > 0.15:
                    reasons[i] = f"Matches your interest in {place_name.title()}"

        # --- Rank & select top-N ---
        ranked = np.argsort(final_scores)[::-1]
        if query_idx is not None:
            ranked = ranked[ranked != query_idx]

        top_indices = ranked[:top_n]

        results: list[dict] = []
        for i in top_indices:
            row = self.df.iloc[i]
            results.append({
                "place_name": row["place_name"],
                "description": str(row["description"])[:160] + "...",
                "attractions": [a.strip() for a in str(row["attractions"]).split(",")],
                "image_query": row["image_query"],
                "rating": float(row["rating"]),
                "reason": reasons[i],
                "category": row["category"],
                "best_season": row["best_season"],
                "avg_budget": int(row["avg_budget_per_day"]),
                "score": round(float(final_scores[i]), 4),
            })
        return results

    # ------------------------------------------------------------------
    # Category browsing
    # ------------------------------------------------------------------
    def get_all_categories(self) -> list[str]:
        """Return a sorted list of unique category labels."""
        cats: set[str] = set()
        for raw in self.df["category"].dropna():
            for c in str(raw).split(","):
                c = c.strip().title()
                if c:
                    cats.add(c)
        return sorted(cats)

    def get_by_category(self, category: str, limit: int = 12) -> list[dict]:
        """Return destinations that match a given category, ranked by rating."""
        cat_lower = category.strip().lower()
        mask = self.df["category"].fillna("").str.lower().str.contains(cat_lower)
        filtered = self.df[mask].sort_values("rating", ascending=False).head(limit)

        results: list[dict] = []
        for _, row in filtered.iterrows():
            results.append({
                "place_name": row["place_name"],
                "description": str(row["description"])[:160] + "...",
                "attractions": [a.strip() for a in str(row["attractions"]).split(",")],
                "image_query": row["image_query"],
                "rating": float(row["rating"]),
                "reason": f"Top {category.title()} destination",
                "category": row["category"],
                "best_season": row["best_season"],
                "avg_budget": int(row["avg_budget_per_day"]),
                "score": float(row["rating"] / 5.0),
            })
        return results

    # ------------------------------------------------------------------
    # AI Itinerary Generator
    # ------------------------------------------------------------------
    def generate_itinerary(self, place_name: str, days: int = 3) -> list[dict]:
        """Generate a smart day-by-day trip itinerary from destination data."""
        query = place_name.strip().lower()
        match = self.df[self.df["place_name"].str.lower() == query]

        if match.empty:
            # Fuzzy fallback
            for _, row in self.df.iterrows():
                if query in str(row["place_name"]).lower() or query in str(row["tags"]).lower():
                    match = self.df[self.df.index == row.name]
                    break

        if match.empty:
            return []

        row = match.iloc[0]
        attractions = [a.strip() for a in str(row["attractions"]).split(",") if a.strip()]
        category = str(row.get("category", "")).lower()
        tags = str(row.get("tags", "")).lower()

        # Time-slot templates based on category
        if "beach" in category or "beach" in tags:
            slots = [
                ("🌅 6:00 AM", "Sunrise walk / beach yoga"),
                ("☀️ 9:00 AM", "Explore {attraction}"),
                ("🍽️ 12:30 PM", "Lunch — local seafood cuisine"),
                ("🏖️ 2:00 PM", "Visit {attraction}"),
                ("🌊 4:30 PM", "Water sports / beach relaxation"),
                ("🌇 6:30 PM", "Sunset by the shore"),
                ("🍜 8:00 PM", "Dinner & night market exploration"),
            ]
        elif "mountain" in category or "hill" in category or "adventure" in tags:
            slots = [
                ("🌄 5:30 AM", "Early morning trek / nature walk"),
                ("☕ 8:00 AM", "Breakfast with mountain views"),
                ("🥾 9:30 AM", "Explore {attraction}"),
                ("🍱 1:00 PM", "Packed lunch at scenic viewpoint"),
                ("🏔️ 2:30 PM", "Visit {attraction}"),
                ("📸 5:00 PM", "Photography & leisure"),
                ("🔥 7:30 PM", "Campfire dinner / local restaurant"),
            ]
        elif "heritage" in category or "culture" in category:
            slots = [
                ("🌤️ 7:00 AM", "Early visit to {attraction} (avoid crowds)"),
                ("🏛️ 10:00 AM", "Guided heritage walk"),
                ("🍽️ 12:30 PM", "Traditional cuisine lunch"),
                ("🎭 2:00 PM", "Explore {attraction}"),
                ("🛍️ 4:30 PM", "Local bazaar & souvenir shopping"),
                ("📸 6:00 PM", "Golden-hour photography at monuments"),
                ("🍜 8:00 PM", "Dinner at heritage restaurant"),
            ]
        elif "spiritual" in category:
            slots = [
                ("🙏 5:00 AM", "Morning aarti / prayer ceremony"),
                ("🕉️ 8:00 AM", "Visit {attraction}"),
                ("☕ 10:30 AM", "Traditional breakfast"),
                ("🧘 12:00 PM", "Meditation / yoga session"),
                ("🏛️ 2:30 PM", "Explore {attraction}"),
                ("🌅 5:30 PM", "Evening ceremony at ghat"),
                ("🍽️ 7:30 PM", "Sattvic dinner"),
            ]
        else:
            slots = [
                ("🌤️ 8:00 AM", "Start the day — breakfast"),
                ("🗺️ 9:30 AM", "Explore {attraction}"),
                ("🍽️ 12:30 PM", "Lunch at popular restaurant"),
                ("📍 2:00 PM", "Visit {attraction}"),
                ("📸 4:30 PM", "Leisure & local exploration"),
                ("🌇 6:00 PM", "Sunset / evening walk"),
                ("🍜 8:00 PM", "Dinner & night exploration"),
            ]

        days = max(1, min(days, 7))
        itinerary = []
        attr_idx = 0

        for d in range(1, days + 1):
            day_plan = {
                "day": d,
                "title": f"Day {d}" + (
                    " — Arrival & Explore" if d == 1
                    else f" — Departure" if d == days and days > 1
                    else f" — Deep Dive"
                ),
                "activities": [],
            }

            for time, template in slots:
                if "{attraction}" in template and attractions:
                    activity = template.replace("{attraction}", attractions[attr_idx % len(attractions)])
                    attr_idx += 1
                else:
                    activity = template
                day_plan["activities"].append({"time": time, "activity": activity})

            itinerary.append(day_plan)

        return itinerary

    # ------------------------------------------------------------------
    # Full destination details (for weather, etc.)
    # ------------------------------------------------------------------
    def get_destination_details(self, place_name: str) -> dict | None:
        """Return complete details for a single destination."""
        query = place_name.strip().lower()
        match = self.df[self.df["place_name"].str.lower() == query]
        if match.empty:
            for _, row in self.df.iterrows():
                if query in str(row["place_name"]).lower():
                    match = self.df[self.df.index == row.name]
                    break
        if match.empty:
            return None

        row = match.iloc[0]
        return {
            "place_name": row["place_name"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "category": row["category"],
            "tags": row["tags"],
            "best_season": row["best_season"],
            "avg_budget": int(row["avg_budget_per_day"]),
            "rating": float(row["rating"]),
            "description": str(row["description"]),
            "attractions": [a.strip() for a in str(row["attractions"]).split(",")],
            "state": row.get("state", ""),
            "nearby_places": row.get("nearby_places", ""),
        }

    # ------------------------------------------------------------------
    # Destination comparison
    # ------------------------------------------------------------------
    def compare_destinations(self, names: list[str]) -> list[dict]:
        """Return comparison data for multiple destinations."""
        results = []
        for name in names[:4]:  # Max 4
            details = self.get_destination_details(name)
            if details:
                results.append(details)
        return results


# ---------------------------------------------------------------------------
# Singleton instance — loaded once at server start
# ---------------------------------------------------------------------------
_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "travel_destinations.csv")
RECOMMENDER = TravelRecommender(_DATA_PATH)
