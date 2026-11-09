"""Build a plain metadata dict from a book for embedding into the EPUB OPF.

``build_epub_metadata`` is the only Django-aware entry point here; it produces a
plain dict that the (Django-free) epub_fix package consumes. ``verify_epub_metadata``
reads an EPUB's OPF back and reports which synced fields do not match, used at
Check B during a safe move.
"""

import re

_AUTHOR_SPLIT = re.compile(r"\s*;\s*|\s+and\s+", re.IGNORECASE)


def build_epub_metadata(book):
    """Return a plain dict of the book's curated metadata for OPF embedding.

    Empty values are omitted. ``authors`` is a list of ``{"name", "file_as"}``
    dicts in a stable order.
    """
    meta = {}
    final = book.final_metadata
    if final is None:
        return meta

    if final.final_title:
        meta["title"] = final.final_title
    authors = _authors(book, final)
    if authors:
        meta["authors"] = authors
    if final.language:
        meta["language"] = final.language
    if final.final_publisher:
        meta["publisher"] = final.final_publisher
    if final.publication_year:
        meta["year"] = final.publication_year
    if final.description:
        meta["description"] = final.description
    subjects = _subjects(book)
    if subjects:
        meta["subjects"] = subjects
    if final.isbn:
        meta["isbn"] = final.isbn
    if final.final_series:
        meta["series"] = final.final_series
    if final.final_series_number:
        meta["series_index"] = final.final_series_number
    return meta


def _authors(book, final):
    """Author entries from main relationships, else from final_author text."""
    rels = list(
        book.author_relationships.filter(is_active=True, is_main_author=True)
        .select_related("author")
        .order_by("-confidence", "id")
    )
    if rels:
        result = []
        for rel in rels:
            author = rel.author
            if not author or not author.name:
                continue
            entry = {"name": author.name}
            file_as = _file_as(author)
            if file_as:
                entry["file_as"] = file_as
            result.append(entry)
        if result:
            return result
    parts = [p.strip() for p in _AUTHOR_SPLIT.split(final.final_author or "") if p.strip()]
    return [{"name": p} for p in parts]


def _file_as(author):
    """'Last, First' from the Author model's names (or whichever part exists)."""
    first = (author.first_name or "").strip()
    last = (author.last_name or "").strip()
    if last and first:
        return f"{last}, {first}"
    return last or first or ""


def _subjects(book):
    return [
        rel.genre.name
        for rel in book.genre_relationships.filter(is_active=True)
        .select_related("genre")
        .order_by("-confidence", "genre__name")
        if rel.genre and rel.genre.name
    ]


def _number_str(value):
    try:
        f = float(value)
    except (ValueError, TypeError):
        return None
    if f == int(f):
        return str(int(f))
    return str(f)


def verify_epub_metadata(epub_path, metadata):
    """Read the EPUB's OPF back and return the list of synced fields whose value
    does not match ``metadata`` (empty list means every field verified)."""
    from books.utils.epub_check.reader import EpubReader

    OPF_NS = "http://www.idpf.org/2007/opf"
    DC_NS = "http://purl.org/dc/elements/1.1/"
    mismatches = []

    reader = EpubReader(str(epub_path))
    try:
        root = reader.opf_root
    except Exception:
        root = None
    finally:
        reader.close()

    def _norm(v):
        return (v or "").strip()

    if root is None:
        return list(metadata.keys()) or ["title"]
    metadata_el = root.find("opf:metadata", {"opf": OPF_NS})
    if metadata_el is None:
        return list(metadata.keys()) or ["title"]

    def _dc(local):
        el = metadata_el.find(f"{{{DC_NS}}}{local}")
        return el.text if el is not None else None

    if "title" in metadata and _norm(_dc("title")) != _norm(metadata["title"]):
        mismatches.append("title")
    if "language" in metadata:
        if (_dc("language") or "").strip().lower() != str(metadata["language"]).strip().lower():
            mismatches.append("language")
    if "publisher" in metadata and _norm(_dc("publisher")) != _norm(metadata["publisher"]):
        mismatches.append("publisher")
    if "description" in metadata and _norm(_dc("description")) != _norm(metadata["description"]):
        mismatches.append("description")
    if "year" in metadata:
        try:
            expected_year = str(int(metadata["year"]))
        except (ValueError, TypeError):
            expected_year = str(metadata["year"])
        if not (_dc("date") or "").startswith(expected_year):
            mismatches.append("year")
    if "authors" in metadata:
        from books.utils.epub_fix.fixer import _creator_role

        author_creators = [
            c for c in metadata_el.findall(f"{{{DC_NS}}}creator")
            if _creator_role(metadata_el, c) in (None, "aut")
        ]
        got = [_norm(c.text) for c in author_creators]
        want = [_norm(a.get("name")) for a in metadata["authors"] if a.get("name")]
        if got != want:
            mismatches.append("authors")
    if "subjects" in metadata:
        got = [_norm(s.text) for s in metadata_el.findall(f"{{{DC_NS}}}subject")]
        want = [_norm(s) for s in metadata["subjects"]]
        if got != want:
            mismatches.append("subjects")
    if "isbn" in metadata:
        isbn = str(metadata["isbn"])
        found = False
        for ident in metadata_el.findall(f"{{{DC_NS}}}identifier"):
            if ident.get(f"{{{OPF_NS}}}scheme") == "ISBN" and _norm(ident.text) == _norm(isbn):
                found = True
            if (ident.text or "").startswith("urn:isbn:") and _norm(ident.text) == _norm(f"urn:isbn:{isbn}"):
                found = True
        if not found:
            mismatches.append("isbn")
    if "series" in metadata:
        got = None
        for mm in metadata_el.findall(f"{{{OPF_NS}}}meta"):
            if mm.get("name") == "calibre:series":
                got = mm.get("content")
        if _norm(got) != _norm(metadata["series"]):
            mismatches.append("series")
    if "series_index" in metadata:
        got = None
        for mm in metadata_el.findall(f"{{{OPF_NS}}}meta"):
            if mm.get("name") == "calibre:series_index":
                got = mm.get("content")
        want = _number_str(metadata["series_index"])
        if want is not None and _norm(got) != _norm(want):
            mismatches.append("series_index")
    return mismatches
