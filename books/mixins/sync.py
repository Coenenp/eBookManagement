"""
Model synchronization mixins for books app.
"""

import logging

logger = logging.getLogger(__name__)


class FinalMetadataSyncMixin:
    """
    Mixin for models that contribute to FinalMetadata.

    Automatically triggers FinalMetadata re-sync when:
    - New metadata is added (on creation)
    - Metadata is updated (confidence changes, source changes)
    - Metadata is deactivated (is_active = False)

    This ensures FinalMetadata always reflects the highest-confidence
    active metadata from all sources.
    """

    def post_deactivation_sync(self):
        """
        Trigger FinalMetadata re-sync after this metadata changes.

        Called automatically by save() when metadata is added, updated,
        or deactivated. This ensures FinalMetadata always shows the
        best available metadata.
        """
        if not hasattr(self, "book"):
            logger.warning(
                f"{self.__class__.__name__} has no 'book' attribute for sync"
            )
            return

        if not self.book:
            logger.warning(f"{self.__class__.__name__}.book is None for sync")
            return

        try:
            # Check if FinalMetadata exists
            if hasattr(self.book, "finalmetadata") and self.book.finalmetadata:
                final = self.book.finalmetadata

                # Only sync if not reviewed (unless forced by user later)
                if not final.is_reviewed:
                    logger.debug(
                        f"Triggering FinalMetadata sync from {self.__class__.__name__} change",
                        extra={
                            "book_id": self.book.id,
                            "metadata_type": self.__class__.__name__,
                            "is_active": getattr(self, "is_active", None),
                            "confidence": getattr(self, "confidence", None),
                        },
                    )
                    # Explicitly sync (save_after=True by default)
                    final.sync_from_sources(save_after=True)
                else:
                    logger.debug(
                        "Skipped FinalMetadata sync - book is reviewed",
                        extra={"book_id": self.book.id},
                    )
            else:
                logger.debug(
                    f"No FinalMetadata exists for book {self.book.id} - skipping sync"
                )

        except Exception as e:
            logger.error(
                f"Error in post_deactivation_sync for {self.__class__.__name__}",
                extra={"book_id": self.book.id if self.book else None, "error": str(e)},
                exc_info=True,
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        abstract = True
