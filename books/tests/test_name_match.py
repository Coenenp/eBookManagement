"""Tests for the name-agreement helper (title/author vs file path)."""

from django.test import SimpleTestCase

from books.utils.name_match import STOP_TOKENS, name_agrees, name_tokens


class NameTokensTests(SimpleTestCase):
    def test_folds_accents_and_case(self):
        self.assertEqual(name_tokens("Rav Grewal-Kök"), ["rav", "grewal", "kok"])
        self.assertEqual(name_tokens("RAV GREWAL-KOK"), ["rav", "grewal", "kok"])
        self.assertEqual(name_tokens("Rav Grewal-Kök"), name_tokens("Rav Grewal-Kok"))

    def test_runs_of_letters_and_digits_at_least_three(self):
        # Runs shorter than 3 characters are dropped ("a", "by", "02").
        self.assertEqual(name_tokens("A by 02 LIVE FREE OR DIE"), ["live", "free", "die"])

    def test_stop_tokens_removed(self):
        self.assertEqual(name_tokens("The Book of Unknown Novel retail epub"), [])
        self.assertEqual(name_tokens("The Great Gatsby"), ["great", "gatsby"])

    def test_empty_text_yields_no_tokens(self):
        self.assertEqual(name_tokens(""), [])
        self.assertEqual(name_tokens("..."), [])


class NameAgreesTests(SimpleTestCase):
    def test_every_wrong_match_example_rejected(self):
        cases = [
            # (title, author, source_path) from the evidence; all are wrong matches.
            (
                "10 Marchfield Square",
                "Nicola Whyte",
                "Assorted Mystery and Thriller Books Collection/The Snares by Rav Grewal-Kök.epub",
            ),
            (
                "Midnight Sun",
                "Stephenie Meyer",
                "USA Today Best-Selling Books/02. LIVE FREE OR DIE by Sean Hannity.epub",
            ),
            (
                "The Magnificent Ambersons",
                "Booth Tarkington",
                "Pulitzer Prize for Fiction/1940 - The Grapes of Wrath - John Steinbeck.epub",
            ),
            (
                "A Crack in the Sky",
                "Mark Peter Hughes",
                "Various/Nightmare - Robin Parrish.epub",
            ),
            (
                "A Match for Lilah Jo",
                "Marisa Masterson",
                "Assorted Romance Books Collection/How Freaking Romantic by Emily Harding.epub",
            ),
        ]
        for title, author, path in cases:
            self.assertFalse(
                name_agrees(title, author, path),
                f"wrong match must not agree: {title!r} | {author!r} | {path!r}",
            )

    def test_every_matching_example_accepted(self):
        cases = [
            (
                "Dexter Is Delicious",
                "Jeff Lindsay",
                "folder/Dexter Is Delicious - Jeff Lindsay.epub",
            ),
            (
                "The Sunlit Man",
                "Brandon Sanderson",
                "folder/The Sunlit Man by Brandon Sanderson.epub",
            ),
            (
                "The Godborn",
                "Paul S. Kemp",
                "Sundering, The\uA789 02/Sundering, The\uA789 02 - The Godborn [Paul S. Kemp] (retail).epub",
            ),
            # Accents must not matter: stored author "Kok" vs path "Kök".
            (
                "The Snares",
                "Rav Grewal-Kok",
                "folder/Rav Grewal-Kök - The Snares.epub",
            ),
        ]
        for title, author, path in cases:
            self.assertTrue(
                name_agrees(title, author, path),
                f"matching pair must agree: {title!r} | {author!r} | {path!r}",
            )

    def test_author_only_agreement_rejected(self):
        # The folder carries the author's surname; the title shares no token.
        # Under the title-first rule the author alone no longer passes.
        self.assertFalse(
            name_agrees(
                "Blood Fever",
                "Charles Higson",
                "Charlie Higson/Higson, Charlie - [Enemy 2] - The Dead.epub",
            )
        )

    def test_title_token_in_path_passes(self):
        # The title shares a token with the path even though the author differs.
        self.assertTrue(
            name_agrees(
                "The Dead",
                "Someone Else",
                "Charlie Higson/Higson, Charlie - [Enemy 2] - The Dead.epub",
            )
        )

    def test_title_with_no_usable_token_falls_back_to_author(self):
        # The title is all stop tokens ("The Book"), so the author rule applies.
        self.assertTrue(
            name_agrees(
                "The Book",
                "Charles Higson",
                "Charlie Higson/Higson, Charlie - [Enemy 2] - The Dead.epub",
            )
        )

    def test_neither_title_nor_author_in_path_rejected(self):
        self.assertFalse(
            name_agrees(
                "Blood Fever",
                "Charles Higson",
                "Some Other Folder/Entirely Different - Unknown Author.epub",
            )
        )

    def test_match_through_title_only(self):
        self.assertTrue(
            name_agrees(
                "Dexter Is Delicious",
                "Some Other Writer",
                "folder/Dexter Is Delicious - Jeff Lindsay.epub",
            )
        )

    def test_only_shared_word_is_stop_token_returns_false(self):
        # "the" / "book" appear in both title and path but are stop tokens.
        self.assertFalse(name_agrees("The Book", "Unknown", "/x/the book.epub"))

    def test_empty_tokens_return_false(self):
        self.assertFalse(name_agrees("", "", "/some/path"))
        self.assertFalse(name_agrees("...", "...", ""))
        self.assertFalse(name_agrees("The Book", "Unknown", ""))


class StopTokensConstantTests(SimpleTestCase):
    def test_stop_tokens_constant_present(self):
        self.assertIsInstance(STOP_TOKENS, (frozenset, set))
        for word in ("the", "and", "for", "with", "from", "van", "der", "het",
                     "een", "von", "des", "les", "une", "epub", "mobi", "pdf",
                     "azw3", "unknown", "book", "novel", "retail", "copy"):
            self.assertIn(word, STOP_TOKENS)
