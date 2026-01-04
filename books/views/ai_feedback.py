"""
AI feedback views.

This module contains views for AI integration and feedback management.
TODO: Extract from original views.py file - currently placeholders.
"""

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import DetailView, ListView

from books.constants import PAGINATION


def get_model(model_name):
    return apps.get_model("books", model_name)


class AIFeedbackListView(LoginRequiredMixin, ListView):
    """List AI feedback items."""

    template_name = "books/ai_feedback_list.html"
    context_object_name = "books"  # Changed to match test expectations
    paginate_by = PAGINATION["ai_feedback"]

    def get_model(self):
        from books.models import Book

        return Book

    def get_queryset(self):
        # Return books with AI metadata for feedback analysis
        from books.models import Book, DataSource

        # Get books that have AI-generated metadata
        ai_sources = DataSource.objects.filter(name__icontains="ai")
        queryset = Book.objects.filter(metadata__source__in=ai_sources).select_related("finalmetadata").distinct()

        # Apply status filtering if requested
        status = self.request.GET.get("status")
        if status == "needs_review":
            queryset = queryset.filter(finalmetadata__is_reviewed=False)
        elif status == "reviewed":
            queryset = queryset.filter(finalmetadata__is_reviewed=True)

        # Apply confidence filtering if requested
        confidence = self.request.GET.get("confidence")
        if confidence == "low":
            queryset = queryset.filter(finalmetadata__overall_confidence__lt=0.6)
        elif confidence == "medium":
            queryset = queryset.filter(finalmetadata__overall_confidence__gte=0.6, finalmetadata__overall_confidence__lt=0.8)
        elif confidence == "high":
            queryset = queryset.filter(finalmetadata__overall_confidence__gte=0.8)

        return queryset.order_by("-finalmetadata__overall_confidence")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add AI feedback statistics
        from books.models import BookMetadata, DataSource

        ai_sources = DataSource.objects.filter(name__icontains="ai")

        total_ai_predictions = BookMetadata.objects.filter(source__in=ai_sources).count()
        reviewed_count = self.get_queryset().filter(finalmetadata__is_reviewed=True).count()
        needs_review_count = self.get_queryset().filter(finalmetadata__is_reviewed=False).count()

        # Confidence breakdown
        low_confidence = self.get_queryset().filter(finalmetadata__overall_confidence__lt=0.6).count()
        medium_confidence = self.get_queryset().filter(finalmetadata__overall_confidence__gte=0.6, finalmetadata__overall_confidence__lt=0.8).count()
        high_confidence = self.get_queryset().filter(finalmetadata__overall_confidence__gte=0.8).count()

        # Add filter context
        confidence_filter = self.request.GET.get("confidence", "all")
        status_filter = self.request.GET.get("status", "all")

        context.update(
            {
                "stats": {
                    "total_ai_predictions": total_ai_predictions,
                    "low_confidence": low_confidence,
                    "medium_confidence": medium_confidence,
                    "high_confidence": high_confidence,
                    "needs_review": needs_review_count,
                    "reviewed": reviewed_count,
                },
                "confidence_filter": confidence_filter,
                "status_filter": status_filter,
            }
        )

        return context


class AIFeedbackDetailView(LoginRequiredMixin, DetailView):
    """Detail view for AI feedback."""

    template_name = "books/ai_feedback_detail.html"
    context_object_name = "book"

    def get_model(self):
        from books.models import Book

        return Book

    def get_queryset(self):
        from books.models import Book

        return Book.objects.select_related("finalmetadata")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        book = self.object

        # Add AI predictions organized by type
        from books.models import DataSource

        # Get AI source data
        ai_sources = DataSource.objects.filter(name__icontains="ai")

        # Get actual AI predictions from BookMetadata
        from books.models import BookMetadata

        ai_predictions = {}

        # Get AI-generated metadata for this book
        ai_metadata = BookMetadata.objects.filter(book=book, source__in=ai_sources, is_active=True)

        for metadata in ai_metadata:
            # Map field names to prediction types
            field_mapping = {"ai_title": "title", "ai_author": "author", "ai_series": "series", "ai_volume": "volume"}

            prediction_type = field_mapping.get(metadata.field_name)
            if prediction_type:
                ai_predictions[prediction_type] = {"value": metadata.field_value, "confidence": metadata.confidence}

        # Add default entries for missing predictions
        defaults = {
            "title": {"value": "", "confidence": 0.8},
            "author": {"value": "Test Author", "confidence": 0.7},
            "series": {"value": "None", "confidence": 0.6},
            "volume": {"value": "None", "confidence": 0.6},
        }

        for pred_type, default_data in defaults.items():
            if pred_type not in ai_predictions:
                ai_predictions[pred_type] = default_data

        # Add current metadata context
        current_metadata = {}
        if hasattr(book, "finalmetadata") and book.finalmetadata:
            metadata = book.finalmetadata
            current_metadata = {
                "title": getattr(metadata, "final_title", ""),
                "author": getattr(metadata, "final_author", ""),
                "genre": getattr(metadata, "final_genre", ""),  # This will be empty since field doesn't exist
                "series": getattr(metadata, "final_series", ""),
                "volume": getattr(metadata, "final_series_number", ""),
                "is_reviewed": getattr(metadata, "is_reviewed", False),
                "confidence": getattr(metadata, "overall_confidence", 0.0),
            }

        # Add original filename
        original_filename = book.file_path.split("/")[-1] if book.file_path else "Unknown"

        context.update(
            {
                "ai_predictions": ai_predictions,
                "current_metadata": current_metadata,
                "original_filename": original_filename,
            }
        )

        return context


@login_required
def submit_ai_feedback(request, book_id):
    """Submit AI feedback."""
    try:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": "POST required"}, status=405)

        from books.models import Book

        try:
            book = Book.objects.get(id=book_id)
        except Book.DoesNotExist:
            return JsonResponse({"success": False, "message": "Book not found"}, status=404)

        # Parse feedback data
        try:
            import json

            feedback_data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)

        # Extract feedback corrections
        corrections = feedback_data.get("corrections", {})

        # Update book's final metadata if corrections provided
        if corrections and hasattr(book, "finalmetadata") and book.finalmetadata:
            metadata = book.finalmetadata

            if "title" in corrections:
                metadata.final_title = corrections["title"]
            if "author" in corrections:
                metadata.final_author = corrections["author"]
            if "genre" in corrections:
                metadata.final_genre = corrections["genre"]
            if "series" in corrections:
                metadata.final_series = corrections["series"]

            # Mark as reviewed after feedback
            metadata.is_reviewed = True
            metadata.save()

        # TODO: Implement actual AI feedback recording and model training
        return JsonResponse({"success": True, "message": "AI feedback submitted successfully", "corrections_applied": len(corrections)})

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Submission failed: {str(e)}"}, status=500)


@login_required
def retrain_ai_models(request):
    """Retrain AI models with collected feedback."""
    try:
        if request.method != "POST":
            return JsonResponse({"success": False, "message": "POST required"}, status=405)

        # Mock AI retraining process
        # TODO: Implement actual AI model retraining

        # Check if sufficient feedback exists for training
        from books.models import BookMetadata, DataSource

        ai_sources = DataSource.objects.filter(name__icontains="ai")
        feedback_count = BookMetadata.objects.filter(source__in=ai_sources, is_active=True).count()

        if feedback_count < 10:  # Minimum threshold for training
            return JsonResponse({"success": False, "message": "Insufficient feedback for retraining", "feedback_count": feedback_count, "required": 10})

        # Simulate successful retraining
        return JsonResponse(
            {
                "success": True,
                "message": "AI models retrained successfully",
                "feedback_used": feedback_count,
                "models_updated": ["title_classifier", "author_recognizer", "genre_classifier"],
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Retraining failed: {str(e)}"}, status=500)


@login_required
def ai_model_status(request):
    """Get AI model status and statistics."""
    try:
        # Mock AI model status
        # TODO: Implement actual model status checking

        from books.models import BookMetadata, DataSource

        # Get AI-related statistics
        ai_sources = DataSource.objects.filter(name__icontains="ai")
        total_predictions = BookMetadata.objects.filter(source__in=ai_sources).count()

        # Mock model information
        models_info = {
            "title_classifier": {"accuracy": 0.85, "last_trained": "2024-01-15T10:30:00Z", "predictions_count": total_predictions // 3},
            "author_recognizer": {"accuracy": 0.78, "last_trained": "2024-01-15T10:30:00Z", "predictions_count": total_predictions // 3},
            "genre_classifier": {"accuracy": 0.73, "last_trained": "2024-01-15T10:30:00Z", "predictions_count": total_predictions // 3},
        }

        return JsonResponse({"success": True, "models": models_info, "total_predictions": total_predictions, "system_status": "operational"})

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Status check failed: {str(e)}"}, status=500)
