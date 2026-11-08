"""Safe EPUB writer: atomic ``.part`` write + ``os.replace``, mimetype first and stored."""

import os
import zipfile
from pathlib import Path

from books.utils.epub_fix.fixer import _compute


def write_epub(source_path, output_path, cover_path=None, fix_encoding=False, metadata=None):
    """Fix and write an EPUB safely, never opening the source for writing.

    Reads the source read-only, applies the lossless fixes and (optionally)
    embeds a cover image, then writes the result to ``output_path``. The
    ``mimetype`` entry is always written first and uncompressed; every other
    entry is deflated. Writes to ``<output>.part`` then atomically replaces the
    target with ``os.replace``; the partial file is removed on any failure.
    """
    src = Path(source_path)
    out = Path(output_path)
    if out.resolve() == src.resolve():
        raise ValueError("output path must differ from the input path")
    _plan, entries, _dropped, _modified = _compute(str(src), cover_path, fix_encoding, metadata)
    _write_entries(str(out), entries)
    return str(out)


def fix_epub(input_path, output_path=None, cover=None, fix_encoding=False):
    """Apply lossless fixes to a new file and return its path.

    Default output is ``<stem>_fixed.epub`` beside the input. Refuses an output
    path equal to the input path.
    """
    src = Path(input_path)
    if output_path is None:
        output_path = src.with_name(src.stem + "_fixed" + src.suffix)
    output_path = Path(output_path)
    if output_path.resolve() == src.resolve():
        raise ValueError("output path must differ from the input path")
    write_epub(src, output_path, cover_path=cover, fix_encoding=fix_encoding)
    return str(output_path)


def _write_entries(output_path, entries):
    part = str(output_path) + ".part"
    try:
        with zipfile.ZipFile(part, "w") as z:
            if "mimetype" in entries:
                z.writestr("mimetype", entries["mimetype"], compress_type=zipfile.ZIP_STORED)
            for name, data in entries.items():
                if name == "mimetype":
                    continue
                z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        # Flush and fsync the .part file before the atomic replace, so the data
        # is durable before the rename becomes visible.
        with open(part, "rb") as f:
            os.fsync(f.fileno())
        os.replace(part, str(output_path))
        # Best-effort fsync of the output directory to persist the rename.
        directory = os.path.dirname(os.path.abspath(str(output_path))) or "."
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
