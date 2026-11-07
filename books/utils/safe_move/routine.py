"""File-level safe move routine.

``safe_move_file`` moves a book file into a new location with a verified
archive copy of the original, so a crash at any point never leaves a book
without a valid file. ``finalize_move`` deletes the library source only after
re-verifying the archive and target; ``rollback_move`` undoes a move.
"""

import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from books.utils.epub_check import check_epub
from books.utils.epub_fix.writer import write_epub
from books.utils.safe_move.archive import archive_destination

# Structural errors the fixer cannot repair: these block the move. Every other
# finding (including HTM-001 malformed XHTML) is flagged, not fatal.
_BLOCKING_CODES = {"MIMETYPE-001", "CONTAINER-001", "OPF-001", "OPF-002", "OPF-003"}

_EPUB_SUFFIXES = (".epub",)
_ZIP_SUFFIXES = (".cbz", ".zip")

_STEP_NAMES = ("planned", "tmp_written", "tmp_verified", "archived", "committed", "finalized")


class NeedsReview(Exception):
    """A book that cannot be moved (blocking check failed). Carries the codes."""

    def __init__(self, codes):
        self.codes = list(codes)
        super().__init__("needs review: " + ", ".join(self.codes))


@dataclass
class MoveResult:
    source: str
    target: str
    archived_path: str
    original_sha256: str
    archived_sha256: str
    new_sha256: str
    repacked: bool
    review_flags: List[str] = field(default_factory=list)
    created_target: bool = False
    tmp_path: str = ""
    on_step: Optional[Callable] = None


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _fsync_file(path):
    with open(path, "rb") as f:
        os.fsync(f.fileno())


def _fsync_dir(path):
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _notify(on_step, name, state):
    if on_step is not None:
        on_step(name, dict(state))


def safe_move_file(source, target, *, scan_root, scan_label, archive_root,
                   repack_epub=True, cover_path=None, fix_encoding=False,
                   on_step=None):
    """Move ``source`` to ``target``, archiving the original. Returns MoveResult."""
    src = Path(source).resolve()
    tgt = Path(target)

    if not src.is_file():
        raise FileNotFoundError(f"source does not exist: {source}")
    if src == tgt.resolve():
        raise ValueError("target must differ from the source")
    if tgt.exists():
        raise FileExistsError(f"target already exists: {target}")

    src_hash = _sha256(src)
    archived_path = archive_destination(str(src), scan_root, scan_label, archive_root)
    tmp = Path(str(tgt) + ".moving")

    state = {
        "source": str(src),
        "target": str(tgt),
        "tmp": str(tmp),
        "archived_path": archived_path,
        "original_sha256": src_hash,
        "repacked": repack_epub and src.suffix.lower() in _EPUB_SUFFIXES,
        "review_flags": [],
        "archived_sha256": None,
        "created_target": False,
    }
    _notify(on_step, "planned", state)

    tgt.parent.mkdir(parents=True, exist_ok=True)
    repacked = False
    if repack_epub and src.suffix.lower() in _EPUB_SUFFIXES:
        try:
            write_epub(str(src), str(tmp), cover_path=cover_path, fix_encoding=fix_encoding)
        except Exception as exc:  # BadZipFile, ValueError, KeyError, lxml errors
            _remove(tmp)
            _remove(str(tmp) + ".part")
            raise NeedsReview([f"repack-failed:{type(exc).__name__}"]) from exc
        repacked = True
    else:
        shutil.copy2(str(src), str(tmp))
        _fsync_file(tmp)
    _notify(on_step, "tmp_written", state)

    # Check A: temporary file exists and is not empty.
    if not tmp.exists() or tmp.stat().st_size == 0:
        _remove(tmp)
        raise NeedsReview(["empty"])

    # Check B: structural verification of the temporary file.
    suffix = src.suffix.lower()
    review_flags: List[str] = []
    if suffix in _EPUB_SUFFIXES:
        report = check_epub(str(tmp))
        blocking = sorted({f.code for f in report.findings if f.code in _BLOCKING_CODES})
        if blocking:
            _remove(tmp)
            raise NeedsReview(blocking)
        review_flags = sorted({f.code for f in report.findings if f.code not in _BLOCKING_CODES})
    elif suffix in _ZIP_SUFFIXES:
        try:
            bad = zipfile.ZipFile(str(tmp)).testzip()
        except (zipfile.BadZipFile, OSError):
            _remove(tmp)
            raise NeedsReview(["zip-corrupt"])
        if bad is not None:
            _remove(tmp)
            raise NeedsReview(["zip-corrupt"])
    else:
        if _sha256(tmp) != src_hash:
            _remove(tmp)
            raise NeedsReview(["hash-mismatch"])

    state["review_flags"] = review_flags
    _notify(on_step, "tmp_verified", state)

    # Archive the original (copy2), then verify the copy matches (check D).
    Path(archived_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), archived_path)
    _fsync_file(archived_path)
    archived_hash = _sha256(archived_path)
    if archived_hash != src_hash:
        _remove(tmp)
        _remove(archived_path)
        raise NeedsReview(["archive-hash"])
    state["archived_sha256"] = archived_hash
    _notify(on_step, "archived", state)

    # Re-check that the target was not created by a concurrent writer between
    # the initial existence check and the atomic replace below.
    if tgt.exists():
        _remove(tmp)
        _remove(str(tmp) + ".part")
        _remove(archived_path)
        raise FileExistsError(f"target already exists: {target}")

    # Commit: atomically replace the target with the verified temporary file.
    os.replace(str(tmp), str(tgt))
    _fsync_dir(tgt.parent)
    state["created_target"] = True
    _notify(on_step, "committed", state)

    result = MoveResult(
        source=str(src),
        target=str(tgt),
        archived_path=archived_path,
        original_sha256=src_hash,
        archived_sha256=archived_hash,
        new_sha256=_sha256(tgt),
        repacked=repacked,
        review_flags=review_flags,
        created_target=True,
        tmp_path=str(tmp),
        on_step=on_step,
    )
    return result


def finalize_move(result):
    """Re-verify the archive copy and target, then delete the library source.

    Raises and deletes nothing when a check fails.
    """
    state = {
        "source": result.source,
        "target": result.target,
        "archived_path": result.archived_path,
        "original_sha256": result.original_sha256,
    }
    if not Path(result.archived_path).is_file():
        raise NeedsReview(["archive-missing"])
    if _sha256(result.archived_path) != result.original_sha256:
        raise NeedsReview(["archive-hash"])
    if not Path(result.target).is_file():
        raise NeedsReview(["target-missing"])
    if _sha256(result.target) != result.new_sha256:
        raise NeedsReview(["target-hash"])

    _notify(result.on_step, "finalized", state)
    os.unlink(result.source)


def rollback_move(result):
    """Undo a move: remove the target (if this call created it), the archive
    copy and any ``.moving``/``.part`` file. The source is left untouched."""
    if result.created_target:
        _remove(result.target)
    _remove(result.archived_path)
    _remove(result.tmp_path)
    _remove(result.tmp_path + ".part")
