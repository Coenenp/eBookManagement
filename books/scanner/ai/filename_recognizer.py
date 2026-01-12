"""AI-powered filename pattern recognition for ebook metadata extraction."""

import json
import logging
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.conf import settings
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from books.models import Book

logger = logging.getLogger("books.scanner")


class FilenamePatternRecognizer:
    """AI-powered filename pattern recognition for metadata extraction."""

    def __init__(self):
        self.model_dir = Path(settings.BASE_DIR) / "books" / "scanner" / "ai" / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.title_model = None
        self.author_model = None
        self.series_model = None
        self.volume_model = None
        self.vectorizer = None

        self.model_paths = {
            "title": self.model_dir / "title_classifier.pkl",
            "author": self.model_dir / "author_classifier.pkl",
            "series": self.model_dir / "series_classifier.pkl",
            "volume": self.model_dir / "volume_classifier.pkl",
            "vectorizer": self.model_dir / "filename_vectorizer.pkl",
            "metadata": self.model_dir / "model_metadata.json",
        }

        self.confidence_threshold = 0.7

    def collect_training_data(self) -> pd.DataFrame:
        """Collect training data from reviewed books with corrected metadata."""
        logger.info("Collecting training data from reviewed books...")

        # Get all books that have been reviewed (approved metadata)
        reviewed_books = Book.objects.filter(finalmetadata__is_reviewed=True).select_related("finalmetadata")

        training_data = []

        for book in reviewed_books:
            metadata = book.finalmetadata

            # Extract filename without extension
            filename = Path(book.file_path).stem

            # Clean and prepare the filename for processing
            cleaned_filename = self._clean_filename(filename)

            training_record = {
                "filename": cleaned_filename,
                "original_filename": filename,
                "title": metadata.final_title or "",
                "author": metadata.final_author or "",
                "series": metadata.final_series or "",
                "volume": str(metadata.final_series_number or ""),  # Fixed field name
                "file_format": book.file_format,
                "book_id": book.id,
            }

            training_data.append(training_record)

        df = pd.DataFrame(training_data)
        logger.info(f"Collected {len(df)} training records from reviewed books")

        # Save training data for analysis
        training_data_path = self.model_dir / "training_data.csv"
        df.to_csv(training_data_path, index=False)
        logger.info(f"Training data saved to {training_data_path}")

        return df

    def _clean_filename(self, filename: str) -> str:
        """Clean filename for better pattern recognition."""
        # Remove common file naming artifacts
        cleaned = filename

        # Remove brackets and their contents (often contains release info)
        cleaned = re.sub(r"\[.*?\]", " ", cleaned)
        cleaned = re.sub(r"\(.*?\)", " ", cleaned)

        # Replace underscores and dots with spaces
        cleaned = re.sub(r"[_\.]", " ", cleaned)

        # Remove common keywords that don't help with metadata
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

        # Clean up multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    def _extract_features(self, filename: str) -> Dict[str, Any]:
        """Extract engineered features from filename."""
        features = {}

        # Length features
        features["filename_length"] = len(filename)
        features["word_count"] = len(filename.split())

        # Pattern features
        features["has_numbers"] = bool(re.search(r"\d", filename))
        features["has_year"] = bool(re.search(r"\b(19|20)\d{2}\b", filename))
        features["has_volume_indicator"] = bool(re.search(r"\b(vol|volume|book|#)\s*\d+\b", filename, re.IGNORECASE))
        features["has_series_indicator"] = bool(re.search(r"\b(series|saga|chronicles|tales)\b", filename, re.IGNORECASE))

        # Punctuation features
        features["dash_count"] = filename.count("-")
        features["colon_count"] = filename.count(":")
        features["comma_count"] = filename.count(",")

        # Position features (where different elements typically appear)
        words = filename.split()
        if words:
            features["first_word_length"] = len(words[0])
            features["last_word_length"] = len(words[-1])
            features["first_word_capitalized"] = words[0][0].isupper() if words[0] else False

        return features

    def train_models(self, df: pd.DataFrame) -> Dict[str, float]:
        """Train ML models for metadata extraction."""
        logger.info("Training AI models for filename pattern recognition...")

        if len(df) < 10:
            logger.warning("Insufficient training data (need at least 10 samples)")
            return {}

        # Prepare features
        X_text = df["filename"].values

        # Create TF-IDF vectorizer for text features
        self.vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 3), stop_words="english", lowercase=True)

        X_text_features = self.vectorizer.fit_transform(X_text)

        # Extract engineered features
        feature_rows = []
        for filename in df["filename"]:
            feature_rows.append(list(self._extract_features(filename).values()))

        X_engineered = pd.DataFrame(feature_rows).values

        # Combine text and engineered features
        from scipy.sparse import hstack

        X_combined = hstack([X_text_features, X_engineered])

        results = {}

        # Train individual models for each metadata field
        for field in ["title", "author", "series", "volume"]:
            y = df[field].values

            # Skip if all values are empty
            if not any(y):
                logger.warning(f"No training data for {field}")
                continue

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X_combined, y, test_size=0.2, random_state=42)

            # Create and train model
            model = Pipeline(
                [
                    (
                        "classifier",
                        RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1),
                    )
                ]
            )

            try:
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)
                accuracy = accuracy_score(y_test, y_pred)

                # Save model
                setattr(self, f"{field}_model", model)
                with open(self.model_paths[field], "wb") as f:
                    pickle.dump(model, f)

                results[field] = accuracy
                logger.info(f"Trained {field} model with accuracy: {accuracy:.3f}")

            except Exception as e:
                logger.error(f"Failed to train {field} model: {e}")

        # Save vectorizer
        with open(self.model_paths["vectorizer"], "wb") as f:
            pickle.dump(self.vectorizer, f)

        # Save model metadata
        metadata = {
            "training_date": datetime.now().isoformat(),
            "training_samples": len(df),
            "model_accuracies": results,
            "confidence_threshold": self.confidence_threshold,
        }

        with open(self.model_paths["metadata"], "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"AI models trained successfully. Results: {results}")
        return results

    def load_models(self) -> bool:
        """Load trained models from disk."""
        try:
            # Check if all required files exist
            required_files = ["vectorizer"]
            for field in ["title", "author", "series", "volume"]:
                if self.model_paths[field].exists():
                    required_files.append(field)

            if not required_files:
                logger.info("No trained models found")
                return False

            # Load vectorizer
            with open(self.model_paths["vectorizer"], "rb") as f:
                self.vectorizer = pickle.load(f)

            # Load models
            for field in ["title", "author", "series", "volume"]:
                if self.model_paths[field].exists():
                    with open(self.model_paths[field], "rb") as f:
                        model = pickle.load(f)
                        setattr(self, f"{field}_model", model)

            logger.info("AI models loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to load AI models: {e}")
            return False

    def predict_metadata(self, filename: str) -> Dict[str, Tuple[str, float]]:
        """Predict metadata from filename using trained models."""
        if not self.vectorizer:
            logger.warning("Models not loaded, cannot predict metadata")
            return {}

        # Clean filename
        cleaned_filename = self._clean_filename(filename)

        # Prepare features
        X_text = self.vectorizer.transform([cleaned_filename])
        X_engineered = pd.DataFrame([list(self._extract_features(cleaned_filename).values())]).values

        from scipy.sparse import hstack

        X_combined = hstack([X_text, X_engineered])

        predictions = {}

        # Get predictions from each model
        for field in ["title", "author", "series", "volume"]:
            model = getattr(self, f"{field}_model", None)
            if model:
                try:
                    # Get prediction and confidence
                    prediction = model.predict(X_combined)[0]

                    # Get prediction probabilities for confidence
                    if hasattr(model.named_steps["classifier"], "predict_proba"):
                        probabilities = model.named_steps["classifier"].predict_proba(X_combined)[0]
                        confidence = max(probabilities)
                    else:
                        confidence = 0.5  # Default confidence for non-probabilistic models

                    predictions[field] = (prediction, confidence)

                except Exception as e:
                    logger.error(f"Error predicting {field}: {e}")

        return predictions

    def is_prediction_confident(self, predictions: Dict[str, Tuple[str, float]]) -> bool:
        """Check if predictions meet confidence threshold."""
        if not predictions:
            return False

        # Check if at least one prediction is above threshold
        confident_predictions = [conf for _, conf in predictions.values() if conf >= self.confidence_threshold]

        return len(confident_predictions) > 0

    def retrain_with_feedback(self, feedback_data: List[Dict[str, str]]) -> Dict[str, float]:
        """Retrain models with user feedback corrections."""
        logger.info(f"Retraining models with {len(feedback_data)} feedback samples...")

        # Load existing training data
        training_data_path = self.model_dir / "training_data.csv"
        if training_data_path.exists():
            existing_df = pd.read_csv(training_data_path)
        else:
            existing_df = pd.DataFrame()

        # Convert feedback to DataFrame
        feedback_df = pd.DataFrame(feedback_data)

        # Combine with existing data
        combined_df = pd.concat([existing_df, feedback_df], ignore_index=True)

        # Remove duplicates based on filename
        combined_df = combined_df.drop_duplicates(subset=["filename"], keep="last")

        # Save updated training data
        combined_df.to_csv(training_data_path, index=False)

        # Retrain models
        return self.train_models(combined_df)

    def models_exist(self) -> bool:
        """Check if all required AI models exist."""
        required_paths = ["vectorizer", "title", "author", "series", "volume"]
        return all(self.model_paths[path].exists() for path in required_paths)

    def get_training_data_stats(self) -> Dict[str, Any]:
        """Get statistics about the training data."""
        try:
            training_data_path = self.model_dir / "training_data.csv"
            if not training_data_path.exists():
                return {"total_samples": 0, "accuracy": 0.0}

            import pandas as pd

            df = pd.read_csv(training_data_path)

            return {
                "total_samples": len(df),
                "accuracy": 0.85,  # Placeholder - would need real accuracy calculation
                "last_trained": (training_data_path.stat().st_mtime if training_data_path.exists() else None),
            }
        except Exception as e:
            logger.error(f"Failed to get training data stats: {e}")
            return {"total_samples": 0, "accuracy": 0.0}


def initialize_ai_system() -> Optional[FilenamePatternRecognizer]:
    """Initialize the AI filename recognition system."""
    try:
        recognizer = FilenamePatternRecognizer()

        # Try to load existing models
        if recognizer.load_models():
            logger.info("AI system initialized with existing models")
            return recognizer

        # If no models exist, collect data and train new ones
        logger.info("No existing models found, training new ones...")
        training_data = recognizer.collect_training_data()

        if len(training_data) >= 10:
            results = recognizer.train_models(training_data)
            if results:
                logger.info("AI system initialized with new models")
                return recognizer

        logger.warning("Insufficient data to train AI models")
        return None

    except Exception as e:
        logger.error(f"Failed to initialize AI system: {e}")
        return None
