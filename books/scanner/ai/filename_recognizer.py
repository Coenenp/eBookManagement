"""AI-powered filename pattern recognition for ebook metadata extraction.

This module implements an *ensemble* of classifiers that each propose metadata
from a filename. Ensemble members:

1. **Regex member** — the deterministic ``parse_path_metadata`` parser.
2. **Segment member** — a new segment-level classifier that splits the filename
   into candidate parts and votes on each part's role (title / author / series /
   volume) using several independent heuristics.
3. **Learned member** (optional) — a ``RandomForestClassifier`` trained on
   *segment roles* (a well-posed categorical problem that generalises to unseen
   filenames), rather than the previous approach of trying to memorise exact
   title/author strings.

The final per-field confidence reflects agreement across the ensemble.
"""

import json
import logging
import pickle
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.conf import settings
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from books.models import Book
from books.utils.parsing_helpers import is_probable_author, looks_like_author

logger = logging.getLogger("books.scanner")


class FilenamePatternRecognizer:
    """Ensemble-based filename pattern recognition for ebook metadata."""

    ROLE_TITLE = "title"
    ROLE_AUTHOR = "author"
    ROLE_SERIES = "series"
    ROLE_VOLUME = "volume"
    ROLE_OTHER = "other"

    SEED_DATA_COLUMNS = [
        "filename",
        "original_filename",
        "title",
        "author",
        "series",
        "volume",
        "file_format",
        "book_id",
    ]

    # Names that appear in titles but not usually in author names.
    TITLE_INDICATOR_WORDS = {
        "guide",
        "manual",
        "novel",
        "anthology",
        "collection",
        "complete",
        "adventures",
        "mystery",
        "romance",
        "fantasy",
        "history",
        "story",
        "tale",
        "tales",
    }

    SERIES_INDICATOR_WORDS = {
        "series",
        "saga",
        "chronicles",
        "trilogy",
        "cycle",
        "duology",
    }

    def __init__(self):
        self.model_dir = Path(settings.BASE_DIR) / "books" / "scanner" / "ai" / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.model_paths = {
            "role": self.model_dir / "role_classifier.pkl",
            "metadata": self.model_dir / "model_metadata.json",
        }

        self.confidence_threshold = 0.7

        # Learned segment-role classifier (optional ensemble member).
        self.role_model = None
        self._learned_weight = 0.8

        # Fixed feature order used by the learned classifier.
        self._segment_feature_order = [
            "position_index",
            "position_ratio",
            "is_first",
            "is_last",
            "word_count",
            "char_length",
            "is_numeric",
            "has_digits",
            "has_volume_indicator",
            "has_series_indicator",
            "has_title_indicator",
            "is_probable_author",
            "looks_like_author",
            "starts_with_article",
            "title_case_ratio",
            "has_year",
        ]

    # ------------------------------------------------------------------
    # Training-data collection (feedback / learning loop)
    # ------------------------------------------------------------------

    def collect_training_data(self) -> pd.DataFrame:
        """Collect training data from reviewed books with corrected metadata."""
        logger.info("Collecting training data from reviewed books...")

        reviewed_books = Book.objects.filter(finalmetadata__is_reviewed=True).select_related("finalmetadata")

        training_data = []
        for book in reviewed_books:
            metadata = book.finalmetadata

            filename = Path(book.file_path).stem
            cleaned_filename = self._clean_filename(filename)

            training_data.append(
                {
                    "filename": cleaned_filename,
                    "original_filename": filename,
                    "title": metadata.final_title or "",
                    "author": metadata.final_author or "",
                    "series": metadata.final_series or "",
                    "volume": str(metadata.final_series_number or ""),
                    "file_format": book.file_format,
                    "book_id": book.id,
                }
            )

        df = pd.DataFrame(training_data)
        logger.info(f"Collected {len(df)} training records from reviewed books")

        training_data_path = self.model_dir / "training_data.csv"
        df.to_csv(training_data_path, index=False)
        logger.info(f"Training data saved to {training_data_path}")

        return df

    def load_seed_training_data(self) -> pd.DataFrame:
        """Load the checked-in seed training corpus."""
        seed_path = self.model_dir / "training_data.csv"
        if not seed_path.exists():
            logger.info("No seed training data file found at %s", seed_path)
            return pd.DataFrame(columns=self.SEED_DATA_COLUMNS)

        try:
            df = pd.read_csv(seed_path, dtype=str, keep_default_na=False)
        except Exception as e:
            logger.warning("Failed to load seed training data: %s", e)
            return pd.DataFrame(columns=self.SEED_DATA_COLUMNS)

        for column in self.SEED_DATA_COLUMNS:
            if column not in df.columns:
                df[column] = ""

        return df[self.SEED_DATA_COLUMNS].fillna("")

    def save_training_data(self, df: pd.DataFrame) -> None:
        """Persist training data to the model directory CSV."""
        training_data_path = self.model_dir / "training_data.csv"
        df.to_csv(training_data_path, index=False)

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _clean_filename(self, filename: str) -> str:
        """Clean filename for better pattern recognition."""
        cleaned = filename

        # Remove brackets and their contents (often contains release info)
        cleaned = re.sub(r"\[.*?\]", " ", cleaned)
        cleaned = re.sub(r"\(.*?\)", " ", cleaned)

        # Replace underscores and dots with spaces
        cleaned = re.sub(r"[_\.]", " ", cleaned)

        noise_words = [
            "ebook",
            "epub",
            "pdf",
            "mobi",
            "azw3",
            "azw",
            "djvu",
            "retail",
            "published",
            "release",
            "edition",
            "repack",
            "scan",
            "ocr",
            "fixed",
            "converted",
            "calibre",
        ]

        for noise_word in noise_words:
            cleaned = re.sub(r"\b" + re.escape(noise_word) + r"\b", " ", cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _basename(self, filename) -> str:
        """Return the filename stem without path or known extension."""
        name = str(filename or "").strip()
        name = re.split(r"[\\/]", name)[-1]
        name = re.sub(
            r"\.(?:epub|mobi|azw3?|pdf|cbz|cbr|cb7|cbt|txt|djvu|prc|lit|fb2|mp3|m4a|m4b|flac|ogg|opus|wav)$",
            "",
            name,
            flags=re.IGNORECASE,
        )
        return name.strip()

    def _extract_features(self, filename: str) -> Dict[str, Any]:
        """Extract engineered features from a full filename."""
        features = {}

        features["filename_length"] = len(filename)
        features["word_count"] = len(filename.split())

        features["has_numbers"] = bool(re.search(r"\d", filename))
        features["has_year"] = bool(re.search(r"\b(19|20)\d{2}\b", filename))
        features["has_volume_indicator"] = bool(re.search(r"\b(vol|volume|book|#)\s*\d+\b", filename, re.IGNORECASE))
        features["has_series_indicator"] = bool(re.search(r"\b(series|saga|chronicles|tales)\b", filename, re.IGNORECASE))

        features["dash_count"] = filename.count("-")
        features["colon_count"] = filename.count(":")
        features["comma_count"] = filename.count(",")

        words = filename.split()
        if words:
            features["first_word_length"] = len(words[0])
            features["last_word_length"] = len(words[-1])
            features["first_word_capitalized"] = words[0][0].isupper() if words[0] else False

        return features

    # ------------------------------------------------------------------
    # Segment classification (the new ensemble core)
    # ------------------------------------------------------------------

    def _segment_filename(self, cleaned: str) -> List[str]:
        """Split a cleaned filename into candidate segments."""
        parts = re.split(r"\s*(?:-{1,2}|—|–|~|::)\s*", cleaned)
        return [p.strip() for p in parts if p.strip()]

    def _is_volume_segment(self, text: str) -> bool:
        """Return True when a segment is purely a volume/number marker."""
        return bool(re.fullmatch(r"(?:vol(?:ume)?|book|part|issue|#)?\s*\d{1,4}(?:\.\d+)?", text.strip(), re.IGNORECASE))

    def _extract_volume_number(self, text: str) -> Optional[str]:
        match = re.search(r"(\d{1,4}(?:\.\d+)?)", text)
        return match.group(1) if match else None

    def _starts_with_article(self, text: str) -> bool:
        return bool(re.match(r"^(the|a|an)\b", text.strip().lower()))

    def _looks_like_title(self, text: str) -> bool:
        t = text.strip().lower()
        if not t:
            return False
        if self._starts_with_article(t):
            return True
        return any(re.search(rf"\b{re.escape(w)}\b", t) for w in self.TITLE_INDICATOR_WORDS)

    def _title_case_ratio(self, words: List[str]) -> float:
        if not words:
            return 0.0
        return sum(1 for w in words if w[:1].isupper()) / len(words)

    def _segment_features(self, segment: str, index: int, total: int) -> Dict[str, Any]:
        text = segment.strip()
        words = text.split()
        return {
            "position_index": index,
            "position_ratio": index / max(total - 1, 1),
            "is_first": 1 if index == 0 else 0,
            "is_last": 1 if index == total - 1 else 0,
            "word_count": len(words),
            "char_length": len(text),
            "is_numeric": 1 if self._is_volume_segment(text) else 0,
            "has_digits": 1 if re.search(r"\d", text) else 0,
            "has_volume_indicator": 1 if re.search(r"\b(vol|volume|book|part|issue|#)\s*\d", text, re.IGNORECASE) else 0,
            "has_series_indicator": 1 if any(re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE) for w in self.SERIES_INDICATOR_WORDS) else 0,
            "has_title_indicator": 1 if self._looks_like_title(text) else 0,
            "is_probable_author": 1 if is_probable_author(text) else 0,
            "looks_like_author": 1 if looks_like_author(text) else 0,
            "starts_with_article": 1 if self._starts_with_article(text) else 0,
            "title_case_ratio": self._title_case_ratio(words),
            "has_year": 1 if re.search(r"\b(19|20)\d{2}\b", text) else 0,
        }

    def _segment_feature_vector(self, segment: str, index: int, total: int) -> List[Any]:
        features = self._segment_features(segment, index, total)
        return [features[key] for key in self._segment_feature_order]

    # Individual micro-voters (each votes on a segment's role).
    def _vote_volume_series(self, segments: List[str], votes: List[Counter], embedded: Dict[int, str]):
        for i, seg in enumerate(segments):
            if self._is_volume_segment(seg):
                votes[i][self.ROLE_VOLUME] += 1
                embedded[i] = self._extract_volume_number(seg)
                if i > 0:
                    votes[i - 1][self.ROLE_SERIES] += 1
                continue

            # "Mistborn 01" -> series "Mistborn" + volume "01"
            match = re.match(r"^(?P<series>.+?)\s+(?P<num>\d{1,4}(?:\.\d+)?)$", seg)
            if match and not self._looks_like_title(seg):
                votes[i][self.ROLE_SERIES] += 1
                embedded[i] = match.group("num")

    def _vote_author(self, segments: List[str], votes: List[Counter]):
        for i, seg in enumerate(segments):
            if self._is_volume_segment(seg):
                continue
            if re.search(r"\s\d{1,4}(?:\.\d+)?$", seg):
                continue
            if self._looks_like_title(seg):
                continue
            if is_probable_author(seg):
                votes[i][self.ROLE_AUTHOR] += 1

    def _vote_title(self, segments: List[str], votes: List[Counter]):
        for i, seg in enumerate(segments):
            if self._looks_like_title(seg):
                votes[i][self.ROLE_TITLE] += 1

    def _vote_position(self, segments: List[str], votes: List[Counter]):
        n = len(segments)
        if n == 1:
            votes[0][self.ROLE_TITLE] += 1
            return

        if n == 2:
            a0 = is_probable_author(segments[0])
            a1 = is_probable_author(segments[1])
            if a0 and not a1:
                votes[0][self.ROLE_AUTHOR] += 1
                votes[1][self.ROLE_TITLE] += 1
            elif a1 and not a0:
                votes[0][self.ROLE_TITLE] += 1
                votes[1][self.ROLE_AUTHOR] += 1
            else:
                if self._starts_with_article(segments[0]) and not self._starts_with_article(segments[1]):
                    votes[0][self.ROLE_TITLE] += 1
                    votes[1][self.ROLE_AUTHOR] += 1
                elif self._starts_with_article(segments[1]):
                    votes[1][self.ROLE_TITLE] += 1
                    votes[0][self.ROLE_AUTHOR] += 1
                elif len(segments[0].split()) > len(segments[1].split()):
                    votes[0][self.ROLE_TITLE] += 1
                    votes[1][self.ROLE_AUTHOR] += 1
                else:
                    votes[1][self.ROLE_TITLE] += 1
                    votes[0][self.ROLE_AUTHOR] += 1
            return

        # n >= 3: the last segment is often an author name.
        if not self._looks_like_title(segments[-1]) and is_probable_author(segments[-1]) and not self._is_volume_segment(segments[-1]):
            votes[-1][self.ROLE_AUTHOR] += 1

    def _segment_member(self, filename) -> Dict[str, Optional[str]]:
        result = {"title": None, "author": None, "series": None, "volume": None}
        name = self._basename(filename)
        cleaned = self._clean_filename(name)
        segments = self._segment_filename(cleaned)
        if not segments:
            return result

        votes = [Counter() for _ in segments]
        embedded: Dict[int, str] = {}

        self._vote_volume_series(segments, votes, embedded)
        self._vote_author(segments, votes)
        self._vote_title(segments, votes)
        self._vote_position(segments, votes)

        title_parts: List[str] = []
        author_parts: List[str] = []
        series_parts: List[str] = []
        volume: Optional[str] = None

        for i, seg in enumerate(segments):
            role = votes[i].most_common(1)[0][0] if votes[i] else None

            if role == self.ROLE_TITLE:
                title_parts.append(seg)
            elif role == self.ROLE_AUTHOR:
                author_parts.append(seg)
            elif role == self.ROLE_SERIES:
                if i in embedded:
                    series_parts.append(re.sub(r"\s+\d{1,4}(?:\.\d+)?$", "", seg).strip())
                    volume = volume or embedded[i]
                else:
                    series_parts.append(seg)
            elif role == self.ROLE_VOLUME:
                volume = volume or embedded.get(i) or self._extract_volume_number(seg)

        if title_parts:
            result["title"] = " - ".join(title_parts)
        if author_parts:
            result["author"] = ", ".join(author_parts)
        if series_parts:
            result["series"] = series_parts[0]
        if volume is not None:
            result["volume"] = volume

        return result

    def _regex_member(self, filename) -> Dict[str, Optional[str]]:
        from books.scanner.parsing import parse_path_metadata

        result = {"title": None, "author": None, "series": None, "volume": None}
        name = self._basename(filename)
        if not name:
            return result
        try:
            meta = parse_path_metadata(name + ".epub")
        except Exception:
            return result

        authors = meta.get("authors") or []
        result["title"] = meta.get("title")
        result["author"] = authors[0] if authors else None
        result["series"] = meta.get("series")
        result["volume"] = self._stringify_number(meta.get("series_number"))
        return result

    def _learned_member(self, filename) -> Dict[str, Optional[str]]:
        result = {"title": None, "author": None, "series": None, "volume": None}
        if self.role_model is None:
            return result

        name = self._basename(filename)
        cleaned = self._clean_filename(name)
        segments = self._segment_filename(cleaned)
        if not segments:
            return result

        try:
            X = [self._segment_feature_vector(seg, i, len(segments)) for i, seg in enumerate(segments)]
            roles = self.role_model.predict(X)
        except Exception:
            return result

        title_parts: List[str] = []
        author_parts: List[str] = []
        series_parts: List[str] = []
        volume: Optional[str] = None

        for i, seg in enumerate(segments):
            role = roles[i]
            if role == self.ROLE_TITLE:
                title_parts.append(seg)
            elif role == self.ROLE_AUTHOR:
                author_parts.append(seg)
            elif role == self.ROLE_SERIES:
                series_parts.append(seg)
            elif role == self.ROLE_VOLUME:
                volume = self._extract_volume_number(seg)

        if title_parts:
            result["title"] = " - ".join(title_parts)
        if author_parts:
            result["author"] = ", ".join(author_parts)
        if series_parts:
            result["series"] = series_parts[0]
        if volume is not None:
            result["volume"] = volume

        return result

    # ------------------------------------------------------------------
    # Ensemble aggregation and prediction
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(value: str) -> str:
        value = re.sub(r"\s+", " ", str(value).strip().lower())
        return value.strip(" -–—,.;:()[]")

    @staticmethod
    def _stringify_number(value) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _aggregate(self, members: List[Tuple[float, Dict[str, Optional[str]]]]) -> Dict[str, Tuple[str, float]]:
        output = {}
        for field in ("title", "author", "series", "volume"):
            votes: Dict[str, List] = {}
            field_weight = 0.0
            for weight, result in members:
                raw = (result.get(field) or "").strip()
                if not raw:
                    continue
                field_weight += weight
                key = self._normalize(raw)
                if key not in votes:
                    votes[key] = [raw, 0.0]
                votes[key][1] += weight

            if votes and field_weight > 0:
                _, (display, winning_weight) = max(votes.items(), key=lambda item: item[1][1])
                output[field] = (display, winning_weight / field_weight)

        return output

    def predict_metadata(self, filename: str) -> Dict[str, Tuple[str, float]]:
        """Predict metadata from a filename using the classifier ensemble."""
        if not filename or not str(filename).strip():
            return {}

        members: List[Tuple[float, Dict[str, Optional[str]]]] = [
            (1.0, self._regex_member(filename)),
            (1.0, self._segment_member(filename)),
        ]

        if self.role_model is not None:
            members.append((self._learned_weight, self._learned_member(filename)))

        return self._aggregate(members)

    def is_prediction_confident(self, predictions: Dict[str, Tuple[str, float]]) -> bool:
        """Check whether at least one prediction meets the confidence threshold."""
        if not predictions:
            return False
        confident = [conf for _, conf in predictions.values() if conf >= self.confidence_threshold]
        return len(confident) > 0

    # ------------------------------------------------------------------
    # Learned classifier training / persistence
    # ------------------------------------------------------------------

    def _tokens_subset(self, segment: str, author: str) -> bool:
        seg_tokens = set(re.findall(r"[a-z0-9]+", segment.lower()))
        author_tokens = set(re.findall(r"[a-z0-9]+", author.lower()))
        return bool(seg_tokens) and seg_tokens.issubset(author_tokens)

    def _derive_segment_role(self, segment: str, title: str, author: str, series: str, volume: str) -> str:
        seg = segment.strip().lower()
        title_l = (title or "").strip().lower()
        author_l = (author or "").strip().lower()
        series_l = (series or "").strip().lower()
        vol_l = str(volume or "").strip().lower()

        if self._is_volume_segment(segment):
            return self.ROLE_VOLUME

        number = self._extract_volume_number(segment)
        if vol_l and number and number == vol_l:
            return self.ROLE_VOLUME

        if series_l and (seg in series_l or series_l in seg):
            return self.ROLE_SERIES

        if author_l and (seg in author_l or self._tokens_subset(seg, author_l)):
            return self.ROLE_AUTHOR

        if title_l and (seg in title_l or title_l in seg):
            return self.ROLE_TITLE

        return self.ROLE_OTHER

    def _build_segment_samples(self, df) -> List[Tuple[List[Any], str]]:
        samples = []
        rows = df.iterrows() if hasattr(df, "iterrows") else ((None, row) for row in df)

        for _, row in rows:
            filename = row.get("filename", "") if hasattr(row, "get") else ""
            if not filename:
                continue
            cleaned = self._clean_filename(self._basename(filename))
            segments = self._segment_filename(cleaned)
            for i, seg in enumerate(segments):
                role = self._derive_segment_role(
                    seg,
                    row.get("title", "") if hasattr(row, "get") else "",
                    row.get("author", "") if hasattr(row, "get") else "",
                    row.get("series", "") if hasattr(row, "get") else "",
                    row.get("volume", "") if hasattr(row, "get") else "",
                )
                samples.append((self._segment_feature_vector(seg, i, len(segments)), role))

        return samples

    def count_segment_samples(self, df) -> int:
        """Return the number of segment-role samples derivable from ``df``."""
        try:
            return len(self._build_segment_samples(df))
        except Exception:
            return 0

    def train_models(self, df) -> Dict[str, float]:
        """Train the learned segment-role classifier from training data."""
        logger.info("Training segment-role classifier...")

        if df is None:
            return {}
        if hasattr(df, "__len__") and len(df) == 0:
            return {}

        samples = self._build_segment_samples(df)
        if len(samples) < 20:
            logger.warning("Insufficient segment samples (need at least 20)")
            return {}

        X = [features for features, _ in samples]
        y = [role for _, role in samples]

        try:
            try:
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
            except Exception:
                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

            model = RandomForestClassifier(n_estimators=100, max_depth=None, random_state=42, n_jobs=-1, class_weight="balanced")
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)

            with open(self.model_paths["role"], "wb") as f:
                pickle.dump(model, f)

            self.role_model = model
            self._learned_weight = min(1.0, max(0.3, accuracy))

            results = {"title": accuracy, "author": accuracy, "series": accuracy, "volume": accuracy}
            metadata = {
                "training_date": datetime.now().isoformat(),
                "training_samples": len(samples),
                "model_accuracies": results,
                "confidence_threshold": self.confidence_threshold,
            }
            with open(self.model_paths["metadata"], "w") as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Segment-role classifier trained. Accuracy: {accuracy:.3f}")
            return results

        except Exception as e:
            logger.error(f"Failed to train segment-role classifier: {e}")
            return {}

    def load_models(self) -> bool:
        """Load the learned segment-role classifier from disk."""
        if not self.model_paths["role"].exists():
            logger.info("No trained segment-role classifier found")
            return False

        try:
            with open(self.model_paths["role"], "rb") as f:
                self.role_model = pickle.load(f)

            self._learned_weight = 0.8
            if self.model_paths["metadata"].exists():
                with open(self.model_paths["metadata"], "r") as f:
                    metadata = json.load(f)
                accuracies = metadata.get("model_accuracies", {})
                if accuracies:
                    self._learned_weight = min(1.0, max(0.3, sum(accuracies.values()) / len(accuracies)))

            logger.info("Segment-role classifier loaded")
            return True

        except Exception as e:
            logger.error(f"Failed to load segment-role classifier: {e}")
            return False

    def models_exist(self) -> bool:
        """Check whether the learned classifier exists."""
        return self.model_paths["role"].exists()

    def get_training_data_stats(self) -> Dict[str, Any]:
        """Return statistics about the training data and learned model."""
        try:
            training_data_path = self.model_dir / "training_data.csv"
            total_samples = 0
            if training_data_path.exists():
                total_samples = len(pd.read_csv(training_data_path))

            accuracy = 0.0
            if self.model_paths["metadata"].exists():
                with open(self.model_paths["metadata"], "r") as f:
                    metadata = json.load(f)
                accuracies = metadata.get("model_accuracies", {})
                if accuracies:
                    accuracy = sum(accuracies.values()) / len(accuracies)

            return {
                "total_samples": total_samples,
                "accuracy": round(accuracy, 3),
                "last_trained": training_data_path.stat().st_mtime if training_data_path.exists() else None,
            }
        except Exception as e:
            logger.error(f"Failed to get training data stats: {e}")
            return {"total_samples": 0, "accuracy": 0.0}

    def retrain_with_feedback(self, feedback_data: List[Dict[str, str]]) -> Dict[str, float]:
        """Retrain the learned classifier with user feedback corrections."""
        logger.info(f"Retraining models with {len(feedback_data)} feedback samples...")

        training_data_path = self.model_dir / "training_data.csv"
        if training_data_path.exists():
            existing_df = pd.read_csv(training_data_path)
        else:
            existing_df = pd.DataFrame()

        feedback_df = pd.DataFrame(feedback_data)
        combined_df = pd.concat([existing_df, feedback_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=["filename"], keep="last")
        combined_df.to_csv(training_data_path, index=False)

        return self.train_models(combined_df)


def initialize_ai_system() -> Optional[FilenamePatternRecognizer]:
    """Initialize the AI filename recognition system.

    The heuristic ensemble is always available; the learned classifier is
    loaded or trained when sufficient data exists.
    """
    try:
        recognizer = FilenamePatternRecognizer()

        if recognizer.load_models():
            logger.info("AI system initialized with existing models")
            return recognizer

        logger.info("No existing models found, training new ones...")
        training_data = recognizer.collect_training_data()

        if len(training_data) >= 10:
            results = recognizer.train_models(training_data)
            if results:
                logger.info("AI system initialized with newly trained models")
                return recognizer

        logger.info("AI system initialized using the heuristic ensemble (no learned model)")
        return recognizer

    except Exception as e:
        logger.error(f"Failed to initialize AI system: {e}")
        return None
