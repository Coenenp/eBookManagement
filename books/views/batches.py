"""Batch list, review, and hold/apply action views.

The read-only list and review pages and the hold / unhold / apply actions all
call the shared service functions in :mod:`books.services.batches`; these views
hold no pipeline logic of their own.  Every writing action redirects back to
the review page and reports its result through Django messages (rendered by the
base template).
"""

import json
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.generic import ListView, View

from books.services.batches import (
    DEFAULT_MANIFEST_DIR,
    HOLD_REASON_CODES,
    apply_reviewed,
    batch_rows,
    batch_summary,
    list_batches,
    reject_books,
    remove_holds,
)


def _manifest_dir():
    """The manifest folder (overridable in tests via ``BATCH_MANIFEST_DIR``)."""
    override = getattr(settings, "BATCH_MANIFEST_DIR", None)
    if override:
        return Path(override)
    return DEFAULT_MANIFEST_DIR


def _resolve_manifest(raw):
    """Resolve a URL batch id to its manifest path; 404 on unknown/malformed.

    A UUID pattern is the only value that may reach a path.  Anything else
    (traversal, malformed, missing) is 404 before any path is built.  This is
    the single shared batch-id check for every batch view.
    """
    try:
        batch_id = str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        raise Http404("unknown batch")
    path = _manifest_dir() / f"{batch_id}.json"
    if not path.is_file():
        raise Http404("unknown batch")
    return batch_id, path


class BatchListView(LoginRequiredMixin, ListView):
    template_name = "books/batches/list.html"
    context_object_name = "batches"

    def get_queryset(self):
        from datetime import datetime

        batches = list_batches(manifest_dir=_manifest_dir())
        for b in batches:
            b["created"] = datetime.fromtimestamp(b["created"])
        return batches

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Batches"
        return context


class BatchReviewView(LoginRequiredMixin, View):
    template_name = "books/batches/review.html"
    http_method_names = ["get"]  # GET only; anything else is 405.

    def get(self, request, batch_id):
        batch_id, manifest_path = _resolve_manifest(batch_id)
        data = json.loads(manifest_path.read_text())
        rows = batch_rows(manifest_path)
        summary = batch_summary(manifest_path)

        context = {
            "page_title": f"Batch {batch_id}",
            "batch_id": batch_id,
            "status": data.get("status"),
            "applied_at": data.get("applied_at"),
            "approve": summary["approve"],
            "hold": summary["hold"],
            "not_approved": summary["not_approved"],
            "rows": rows,
            "hold_reason_codes": HOLD_REASON_CODES,
        }
        return render(request, self.template_name, context)


class _BatchActionView(LoginRequiredMixin, View):
    """Shared POST-only base for the hold / unhold / apply actions.

    Resolves the batch id (one shared check), runs the sub-view's ``_act``,
    reports a refusal as an error message or a success message, and redirects
    back to the review page.
    """

    http_method_names = ["post"]

    def post(self, request, batch_id):
        batch_id, manifest_path = _resolve_manifest(batch_id)
        result = self._act(request, batch_id, manifest_path)
        if result.get("refusal"):
            messages.error(request, result["refusal"])
        else:
            messages.success(request, result["message"])
        return redirect("books:batch_review", batch_id=batch_id)

    def _act(self, request, batch_id, manifest_path):  # pragma: no cover - abstract
        raise NotImplementedError


class BatchHoldView(_BatchActionView):
    def _act(self, request, batch_id, manifest_path):
        reason = request.POST.get("reason", "")
        if reason not in HOLD_REASON_CODES:
            return {"refusal": f"unknown reason code: {reason}"}
        try:
            book_id = int(request.POST.get("book_id", ""))
        except (TypeError, ValueError):
            return {"refusal": "invalid book id"}
        result = reject_books(str(manifest_path), book_id, reason)
        if result.get("refusal"):
            return result
        return {"message": result["line"]}


class BatchUnholdView(_BatchActionView):
    def _act(self, request, batch_id, manifest_path):
        try:
            book_id = int(request.POST.get("book_id", ""))
        except (TypeError, ValueError):
            return {"refusal": "invalid book id"}
        result = remove_holds([book_id], str(manifest_path))
        if result.get("refusal"):
            return result
        return {"message": f"removed hold for {book_id}"}


class BatchApplyView(_BatchActionView):
    def _act(self, request, batch_id, manifest_path):
        try:
            typed = int(request.POST.get("count", ""))
        except (TypeError, ValueError):
            return {"refusal": "invalid count"}
        result = apply_reviewed(str(manifest_path), typed)
        if result.get("refusal"):
            return result
        return {
            "message": f"approved {result['approved_count']}, "
            f"skipped {result['skipped_count']}"
        }
