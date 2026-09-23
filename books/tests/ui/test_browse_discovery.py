"""M1a-followup Playwright regression tests for the browse/discovery pages.

/series/ and /comics/ were never covered by the M1a walkthrough (only
/books/?q=test was). These tests pin the two filter bugs fixed in this session
so they cannot regress silently again:

- /series/ search must match a book title inside a series, not only the series
  name (series-section.js ``filterItems`` override had dropped the book-title
  search the base class performs).
- /comics/ sort-by-date must actually reorder by ``date_added`` (it previously
  read ``last_scanned``, which the comics endpoint never emits, making the sort
  a silent no-op).

Like the rest of the walkthrough, these run only with RUN_UI_TESTS=1 against a
live server (default port 8001) and read credentials from the environment.
"""

import pytest

pytestmark = pytest.mark.ui


def _wait_for_rows(page, container_selector):
    """Wait until the section list has rendered at least one row."""
    page.wait_for_function(
        f"() => document.querySelector('{container_selector}')?.querySelector('table.condensed-table tbody tr') !== null",
        timeout=15000,
    )


def test_series_page_renders(authenticated_page, app_url):
    page = authenticated_page
    page.goto(f"{app_url}/series/")
    page.wait_for_load_state("networkidle")
    _wait_for_rows(page, "#series-list-container")
    assert "Server Error" not in page.content()


def test_comics_page_renders(authenticated_page, app_url):
    page = authenticated_page
    page.goto(f"{app_url}/comics/")
    page.wait_for_load_state("networkidle")
    _wait_for_rows(page, "#comics-list-container")
    assert "Server Error" not in page.content()


def test_series_search_matches_book_title(authenticated_page, app_url):
    """Searching for a book title must surface its containing series."""
    page = authenticated_page
    page.goto(f"{app_url}/series/")
    page.wait_for_load_state("networkidle")
    _wait_for_rows(page, "#series-list-container")

    # Find a book whose title is NOT a substring of its series name, so the
    # search can only match via the (fixed) book-title path.
    probe = page.evaluate(
        """() => {
            const data = window.seriesManager?.currentData || [];
            for (const s of data) {
                for (const b of (s.books || [])) {
                    const t = (b.title || '').trim();
                    if (t && !s.name.toLowerCase().includes(t.toLowerCase())) {
                        return { series: s.name, title: t };
                    }
                }
            }
            return null;
        }"""
    )
    if probe is None:
        pytest.skip("dataset has no series whose book title differs from the series name")

    page.fill("#search-filter", probe["title"])
    page.wait_for_timeout(800)

    container_text = page.locator("#series-list-container").inner_text()
    assert probe["series"] in container_text, (
        f"searching for book title {probe['title']!r} should keep series {probe['series']!r}"
    )


def test_comics_sort_by_date_reorders(authenticated_page, app_url):
    """Sorting comics by date must reorder them (date_added, not last_scanned)."""
    page = authenticated_page
    page.goto(f"{app_url}/comics/")
    page.wait_for_load_state("networkidle")
    _wait_for_rows(page, "#comics-list-container")

    def series_names():
        return page.locator("table.condensed-table tbody tr td.col-title").all_inner_texts()

    page.select_option("#sort-filter", "title")
    page.wait_for_timeout(400)
    title_order = series_names()

    page.select_option("#sort-filter", "date")
    page.wait_for_timeout(400)
    date_order = series_names()

    assert len(date_order) == len(title_order)
    # Where the dataset has more than one distinct issue date, the two orderings
    # must differ; where every issue shares a date, date-sort == title-sort is
    # acceptable (it must at least not error or drop rows).
    if len(set(date_order)) > 1:
        assert date_order != title_order, "sort-by-date did not reorder the comic series"
