"""Tests for the shared surname-particle splitter in books.utils.surname_particles."""

from collections import Counter

from django.test import TestCase

from books.utils.surname_particles import split_author, sort_name


def _letters(text):
    """Multiset of alphabetic characters, case-insensitive, ignoring everything else."""
    return Counter(c.lower() for c in text if c.isalpha())


class SurnameParticlesTests(TestCase):
    """Behaviour of split_author and sort_name for prefixed surnames."""

    def assert_sort_and_letters(self, full_name, expected_sort):
        first, last = split_author(full_name)
        self.assertEqual(sort_name(full_name), expected_sort)
        # The result is a pure reordering: identical letters, order aside.
        self.assertEqual(_letters(sort_name(full_name)), _letters(full_name))
        # split_author must reassemble to the same letters too.
        self.assertEqual(_letters(f"{last} {first}".strip()), _letters(full_name))

    def test_van_sambeek(self):
        self.assertEqual(split_author("Liza van Sambeek"), ("Liza", "van Sambeek"))
        self.assert_sort_and_letters("Liza van Sambeek", "van Sambeek, Liza")

    def test_van_der_meer_lowercase(self):
        self.assertEqual(split_author("Vonne van der meer"), ("Vonne", "van der meer"))
        self.assert_sort_and_letters("Vonne van der meer", "van der meer, Vonne")

    def test_den_hollander(self):
        self.assertEqual(split_author("Ellen den Hollander"), ("Ellen", "den Hollander"))
        self.assert_sort_and_letters("Ellen den Hollander", "den Hollander, Ellen")

    def test_le_guin(self):
        self.assertEqual(split_author("Ursula K. Le Guin"), ("Ursula K.", "Le Guin"))
        self.assert_sort_and_letters("Ursula K. Le Guin", "Le Guin, Ursula K.")

    def test_van_draanen(self):
        self.assertEqual(split_author("Wendelin Van Draanen"), ("Wendelin", "Van Draanen"))
        self.assert_sort_and_letters("Wendelin Van Draanen", "Van Draanen, Wendelin")

    def test_vincent_van_gogh(self):
        self.assertEqual(split_author("Vincent van Gogh"), ("Vincent", "van Gogh"))
        self.assert_sort_and_letters("Vincent van Gogh", "van Gogh, Vincent")

    def test_van_morrison_two_tokens_capital(self):
        self.assertEqual(split_author("Van Morrison"), ("Van", "Morrison"))
        self.assert_sort_and_letters("Van Morrison", "Morrison, Van")

    def test_vanden_lowercase(self):
        self.assertEqual(split_author("Jan vanden Berg"), ("Jan", "vanden Berg"))
        self.assert_sort_and_letters("Jan vanden Berg", "vanden Berg, Jan")

    def test_vanden_capitalized(self):
        self.assertEqual(split_author("Jan Vanden Berg"), ("Jan", "Vanden Berg"))
        self.assert_sort_and_letters("Jan Vanden Berg", "Vanden Berg, Jan")

    def test_peter_vanden(self):
        self.assertEqual(split_author("Peter Vanden"), ("Peter", "Vanden"))
        self.assert_sort_and_letters("Peter Vanden", "Vanden, Peter")

    def test_comma_last_first(self):
        self.assertEqual(split_author("van der Meer, Vonne"), ("Vonne", "van der Meer"))
        self.assert_sort_and_letters("van der Meer, Vonne", "van der Meer, Vonne")

    def test_comma_trailing_particle_moves(self):
        self.assertEqual(split_author("Sambeek, Liza van"), ("Liza", "van Sambeek"))
        self.assert_sort_and_letters("Sambeek, Liza van", "van Sambeek, Liza")

    def test_de_nore(self):
        self.assertEqual(split_author("Annel de Nore"), ("Annel", "de Nore"))
        self.assert_sort_and_letters("Annel de Nore", "de Nore, Annel")

    def test_d_apostrophe(self):
        self.assertEqual(split_author("Christine d'Ormesson"), ("Christine", "d'Ormesson"))
        self.assert_sort_and_letters("Christine d'Ormesson", "d'Ormesson, Christine")

    def test_o_apostrophe(self):
        self.assertEqual(split_author("Flann O'Connor"), ("Flann", "O'Connor"))
        self.assert_sort_and_letters("Flann O'Connor", "O'Connor, Flann")

    def test_no_particle_last_word(self):
        self.assertEqual(split_author("Isaac Asimov"), ("Isaac", "Asimov"))
        self.assert_sort_and_letters("Isaac Asimov", "Asimov, Isaac")

    def test_single_word(self):
        self.assertEqual(split_author("Asimov"), ("", "Asimov"))
        self.assertEqual(sort_name("Asimov"), "Asimov")

    def test_empty(self):
        self.assertEqual(split_author(""), ("", ""))
        self.assertEqual(sort_name(""), "")
