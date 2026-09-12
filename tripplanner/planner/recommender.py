"""
Intelligent Travel Recommendation Engine
=========================================
Hybrid ML system combining:
  1. TF-IDF content-based similarity (description + category + tags)
  2. Haversine geographic proximity scoring
  3. Popularity-weighted ranking (normalized ratings)
  4. Category-interest matching for contextual reasons

Built using standard Python data structures (csv, math, re) to eliminate
heavy startup overhead and prevent Vercel 500 FUNCTION_INVOCATION_FAILED
ModuleNotFoundError crashes.
"""

import csv
import math
import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Weights for the hybrid scoring formula
# ---------------------------------------------------------------------------
W_SIMILARITY = 0.60   # TF-IDF cosine similarity
W_POPULARITY = 0.20   # Normalized rating (0-1)
W_PROXIMITY  = 0.15   # Geographic closeness bonus
W_CATEGORY   = 0.05   # Category overlap bonus

PROXIMITY_THRESHOLD_KM = 500.0  # Max distance for proximity bonus

DEFAULT_STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}


class TravelRecommender:
    """Production-level hybrid travel recommendation engine built with pure Python."""

    def __init__(self, data_path: str) -> None:
        self.destinations: list[dict[str, Any]] = []
        self.tfidf_vectors: list[dict[str, float]] = []
        self.idfs: dict[str, float] = {}
        self.norm_ratings: list[float] = []
        self.category_sets: list[set[str]] = []

        self._load_data(data_path)
        self._prepare_features()

    def _load_data(self, data_path: str) -> None:
        """Load destinations dataset from CSV into list of dicts."""
        if not os.path.exists(data_path):
            return

        with open(data_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dest = dict(row)
                try:
                    dest["rating"] = float(dest.get("rating", 0.0))
                except (ValueError, TypeError):
                    dest["rating"] = 0.0

                try:
                    dest["latitude"] = float(dest.get("latitude", 0.0))
                except (ValueError, TypeError):
                    dest["latitude"] = 0.0

                try:
                    dest["longitude"] = float(dest.get("longitude", 0.0))
                except (ValueError, TypeError):
                    dest["longitude"] = 0.0

                try:
                    dest["avg_budget_per_day"] = int(float(dest.get("avg_budget_per_day", 0)))
                except (ValueError, TypeError):
                    dest["avg_budget_per_day"] = 0

                self.destinations.append(dest)

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into unigrams and bigrams, filtering stop words."""
        words = [
            w for w in re.findall(r"\b[a-z0-9]+\b", text.lower())
            if w not in DEFAULT_STOP_WORDS and len(w) > 1
        ]
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
        return words + bigrams

    def _prepare_features(self) -> None:
        """Build TF-IDF matrix over rich combined-text features."""
        n_docs = len(self.destinations)
        if n_docs == 0:
            return

        doc_tokens_list: list[list[str]] = []
        doc_freqs: dict[str, int] = {}
        doc_tfs: list[dict[str, float]] = []

        for dest in self.destinations:
            text = (
                f"{dest.get('description', '')} "
                f"{dest.get('category', '')} "
                f"{dest.get('tags', '')} "
                f"{dest.get('state', '')} "
                f"{dest.get('attractions', '')}"
            ).lower()

            tokens = self._tokenize(text)
            doc_tokens_list.append(tokens)

            tf_counts: dict[str, int] = {}
            for t in tokens:
                tf_counts[t] = tf_counts.get(t, 0) + 1

            tf_sublinear: dict[str, float] = {}
            for t, count in tf_counts.items():
                tf_sublinear[t] = 1.0 + math.log(count)
                doc_freqs[t] = doc_freqs.get(t, 0) + 1

            doc_tfs.append(tf_sublinear)

        # Smooth IDF: log((1 + N) / (1 + df)) + 1
        self.idfs = {
            term: math.log((1.0 + n_docs) / (1.0 + df)) + 1.0
            for term, df in doc_freqs.items()
        }

        # Build normalized TF-IDF vectors
        self.tfidf_vectors = []
        for tf in doc_tfs:
            vec: dict[str, float] = {}
            for t, val in tf.items():
                vec[t] = val * self.idfs[t]

            norm = math.sqrt(sum(v * v for v in vec.values()))
            if norm > 0:
                vec = {t: v / norm for t, v in vec.items()}
            self.tfidf_vectors.append(vec)

        # Pre-compute normalized ratings (0-1 scale)
        self.norm_ratings = [d["rating"] / 5.0 for d in self.destinations]

        # Pre-compute category sets for fast overlap scoring
        self.category_sets = [
            set(c.lower().strip() for c in str(d.get("category", "")).split(",") if c.strip())
            for d in self.destinations
        ]

    def _transform_query(self, query: str) -> dict[str, float]:
        """Convert input query text into a normalized TF-IDF vector."""
        tokens = self._tokenize(query)
        tf_counts: dict[str, int] = {}
        for t in tokens:
            if t in self.idfs:
                tf_counts[t] = tf_counts.get(t, 0) + 1

        vec: dict[str, float] = {}
        for t, count in tf_counts.items():
            vec[t] = (1.0 + math.log(count)) * self.idfs[t]

        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            vec = {t: v / norm for t, v in vec.items()}
        return vec

    @staticmethod
    def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Compute cosine similarity between two normalized TF-IDF dict vectors."""
        if not vec1 or not vec2:
            return 0.0
        if len(vec1) > len(vec2):
            vec1, vec2 = vec2, vec1
        return sum(val * vec2[term] for term, val in vec1.items() if term in vec2)

    @staticmethod
    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return distance in km between two lat/lon points."""
        R = 6371.0  # Earth radius km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
            * math.sin(dlon / 2.0) ** 2
        )
        return 2.0 * R * math.asin(math.sqrt(a))

    def _category_overlap(self, idx: int, other_idx: int) -> float:
        a, b = self.category_sets[idx], self.category_sets[other_idx]
        if not a or not b:
            return 0.0
        return len(a & b) / max(len(a | b), 1)

    def get_recommendations(self, place_name: str, top_n: int = 6) -> list[dict]:
        place_name_clean = place_name.strip().lower()
        n = len(self.destinations)
        if n == 0:
            return []

        # --- Resolve query to a dataset index ---
        query_idx = None
        for idx, dest in enumerate(self.destinations):
            if str(dest.get("place_name", "")).strip().lower() == place_name_clean:
                query_idx = idx
                break

        sim_scores: list[float] = [0.0] * n
        if query_idx is not None:
            q_vec = self.tfidf_vectors[query_idx]
            for i in range(n):
                sim_scores[i] = self._cosine_similarity(q_vec, self.tfidf_vectors[i])
        else:
            q_vec = self._transform_query(place_name_clean)
            for i in range(n):
                sim_scores[i] = self._cosine_similarity(q_vec, self.tfidf_vectors[i])

        final_scores: list[float] = [0.0] * n
        for i in range(n):
            final_scores[i] = (sim_scores[i] * W_SIMILARITY) + (self.norm_ratings[i] * W_POPULARITY)

        reasons: list[str] = ["Recommended for you"] * n
        if query_idx is not None:
            q_lat = self.destinations[query_idx]["latitude"]
            q_lon = self.destinations[query_idx]["longitude"]
            q_name = str(self.destinations[query_idx]["place_name"])
            q_cats = self.category_sets[query_idx]

            for i in range(n):
                if i == query_idx:
                    continue

                dist = self.haversine(
                    q_lat, q_lon,
                    self.destinations[i]["latitude"],
                    self.destinations[i]["longitude"],
                )
                if dist < PROXIMITY_THRESHOLD_KM:
                    prox_bonus = 1.0 - (dist / PROXIMITY_THRESHOLD_KM)
                    final_scores[i] += prox_bonus * W_PROXIMITY

                cat_score = self._category_overlap(query_idx, i)
                final_scores[i] += cat_score * W_CATEGORY

                overlap = q_cats & self.category_sets[i]
                if dist < 300:
                    reasons[i] = f"Near {q_name}"
                elif overlap:
                    shared = ", ".join(sorted(overlap)).title()
                    reasons[i] = f"Matches your interest in {shared.split(',')[0].strip()}"
                elif sim_scores[i] > 0.25:
                    reasons[i] = f"Similar to {q_name}"
        else:
            for i in range(n):
                if sim_scores[i] > 0.15:
                    reasons[i] = f"Matches your interest in {place_name.title()}"

        # Rank indices by final score descending
        candidate_indices = list(range(n))
        if query_idx is not None:
            candidate_indices.remove(query_idx)

        candidate_indices.sort(key=lambda i: final_scores[i], reverse=True)
        top_indices = candidate_indices[:top_n]

        results: list[dict] = []
        for i in top_indices:
            row = self.destinations[i]
            results.append({
                "place_name": row["place_name"],
                "description": str(row.get("description", ""))[:160] + "...",
                "attractions": [a.strip() for a in str(row.get("attractions", "")).split(",") if a.strip()],
                "image_query": row.get("image_query", ""),
                "rating": float(row.get("rating", 0.0)),
                "reason": reasons[i],
                "category": row.get("category", ""),
                "best_season": row.get("best_season", ""),
                "avg_budget": int(row.get("avg_budget_per_day", 0)),
                "score": round(float(final_scores[i]), 4),
            })
        return results

    def get_all_categories(self) -> list[str]:
        """Return a sorted list of unique category labels."""
        cats: set[str] = set()
        for dest in self.destinations:
            raw = dest.get("category", "")
            if raw:
                for c in str(raw).split(","):
                    c = c.strip().title()
                    if c:
                        cats.add(c)
        return sorted(cats)

    def get_by_category(self, category: str, limit: int = 12) -> list[dict]:
        """Return destinations that match a given category, ranked by rating."""
        cat_lower = category.strip().lower()
        matched = [
            d for d in self.destinations
            if cat_lower in str(d.get("category", "")).lower()
        ]
        matched.sort(key=lambda d: d.get("rating", 0.0), reverse=True)
        filtered = matched[:limit]

        results: list[dict] = []
        for row in filtered:
            results.append({
                "place_name": row["place_name"],
                "description": str(row.get("description", ""))[:160] + "...",
                "attractions": [a.strip() for a in str(row.get("attractions", "")).split(",") if a.strip()],
                "image_query": row.get("image_query", ""),
                "rating": float(row.get("rating", 0.0)),
                "reason": f"Top {category.title()} destination",
                "category": row.get("category", ""),
                "best_season": row.get("best_season", ""),
                "avg_budget": int(row.get("avg_budget_per_day", 0)),
                "score": float(row.get("rating", 0.0) / 5.0),
            })
        return results

    def generate_itinerary(self, place_name: str, days: int = 3) -> list[dict]:
        """Generate a smart day-by-day trip itinerary from destination data."""
        query = place_name.strip().lower()
        match_dest = None

        for dest in self.destinations:
            if str(dest.get("place_name", "")).strip().lower() == query:
                match_dest = dest
                break

        if match_dest is None:
            for dest in self.destinations:
                pname = str(dest.get("place_name", "")).lower()
                tags = str(dest.get("tags", "")).lower()
                if query in pname or query in tags:
                    match_dest = dest
                    break

        if match_dest is None:
            return []

        attractions = [a.strip() for a in str(match_dest.get("attractions", "")).split(",") if a.strip()]
        category = str(match_dest.get("category", "")).lower()
        tags = str(match_dest.get("tags", "")).lower()

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
                    else " — Departure" if d == days and days > 1
                    else " — Deep Dive"
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

    def get_destination_details(self, place_name: str) -> dict | None:
        """Return complete details for a single destination."""
        query = place_name.strip().lower()
        match_dest = None

        for dest in self.destinations:
            if str(dest.get("place_name", "")).strip().lower() == query:
                match_dest = dest
                break

        if match_dest is None:
            for dest in self.destinations:
                if query in str(dest.get("place_name", "")).lower():
                    match_dest = dest
                    break

        if match_dest is None:
            return None

        return {
            "place_name": match_dest["place_name"],
            "latitude": float(match_dest["latitude"]),
            "longitude": float(match_dest["longitude"]),
            "category": match_dest.get("category", ""),
            "tags": match_dest.get("tags", ""),
            "best_season": match_dest.get("best_season", ""),
            "avg_budget": int(match_dest.get("avg_budget_per_day", 0)),
            "rating": float(match_dest.get("rating", 0.0)),
            "description": str(match_dest.get("description", "")),
            "attractions": [a.strip() for a in str(match_dest.get("attractions", "")).split(",") if a.strip()],
            "state": match_dest.get("state", ""),
            "nearby_places": match_dest.get("nearby_places", ""),
        }

    def compare_destinations(self, names: list[str]) -> list[dict]:
        """Return comparison data for multiple destinations."""
        results = []
        for name in names[:4]:  # Max 4
            details = self.get_destination_details(name)
            if details:
                results.append(details)
        return results

    def get_dataframe(self):
        """Optional lazy import of pandas DataFrame if needed."""
        try:
            import pandas as pd
            return pd.DataFrame(self.destinations)
        except ImportError:
            raise RuntimeError("pandas is not installed in the current environment.")

    @property
    def df(self):
        """Backwards compatibility property for DataFrame access."""
        return self.get_dataframe()


# ---------------------------------------------------------------------------
# Singleton instance — loaded once at server start
# ---------------------------------------------------------------------------
_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "travel_destinations.csv")
RECOMMENDER = TravelRecommender(_DATA_PATH)
