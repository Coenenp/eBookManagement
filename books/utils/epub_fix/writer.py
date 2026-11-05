"""Safe EPUB writer: atomic ``.part`` write + ``os.replace``, mimetype first and stored."""

import os
import zipfile
from pathlib import Path

from books.utils.epub_fix.fixer import _compute


def write_epub(source_path, output_path, cover_path=None):
    """Fix and write an EPUB safely, never opening the source for writing.

    Reads the source read-only, applies the lossless fixes and (optionally)
    embeds a cover image, then writes the result to ``output_path``. The
    ``mimetype`` entry is always written first and uncompressed; every other
    entry is deflated. Writes to ``<output>.part`` then atomically replaces the
    target with ``os.replace``; the partial file is removed on any failure.
    """
    _plan, entries, _dropped, _modified = _compute(str(source_path), cover_path)
    _write_entries(str(output_path), entries)
    return str(output_path)


def fix_epub(input_path, output_path=None, cover=None):
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
    write_epub(src, output_path, cover_path=cover)
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
        os.replace(part, str(output_path))
    except Exception:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
