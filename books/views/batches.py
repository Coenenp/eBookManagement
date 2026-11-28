"""Read-only batch list and batch review views.

These views expose the batch pipeline (section 4d) through the shared service
functions ``list_batches``, ``batch_rows`` and ``read_holds`` only; they hold
no pipeline logic of their own.  They are read only: GET renders a page, any
other method is refused (405).  The hold toggle and the apply screen land in
the next PR.
"""

import json
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import render
from django.views.generic import ListView, View

from books.services.batches import DEFAULT_MANIFEST_DIR, batch_rows, list_batches


def _manifest_dir():
    """The manifest folder (overridable in tests via ``BATCH_MANIFEST_DIR``)."""
    override = getattr(settings, "BATCH_MANIFEST_DIR", None)
    if override:
        return Path(override)
    return DEFAULT_MANIFEST_DIR


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

    def _batch_id(self, raw):
        # A UUID pattern is the only value that may reach a path.  Anything
        # else (traversal, malformed, missing) is 404 before any path is built.
        try:
            return str(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError):
            raise Http404("unknown batch")

    def get(self, request, batch_id):
        batch_id = self._batch_id(batch_id)
        manifest_path = _manifest_dir() / f"{batch_id}.json"
        if not manifest_path.is_file():
            raise Http404("unknown batch")

        data = json.loads(manifest_path.read_text())
        rows = batch_rows(manifest_path)

        approve = sum(1 for r in rows if not r["held"])
        hold = sum(1 for r in rows if r["held"])

        context = {
            "page_title": f"Batch {batch_id}",
            "batch_id": batch_id,
            "status": data.get("status"),
            "applied_at": data.get("applied_at"),
            "applied_count": len(data.get("applied_ids", [])),
            "approve": approve,
            "hold": hold,
            "rows": rows,
        }
        return render(request, self.template_name, context)
