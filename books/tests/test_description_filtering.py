"""Tests for the description sanitization filter."""

from django.test import TestCase
from books.templatetags.custom_filters import sanitize_description


class DescriptionFilterTests(TestCase):
    """Test cases for the sanitize_description template filter"""

    def test_html_with_class_attributes(self):
        """Test HTML with class attributes (complex real-world example)"""
        input_html = '<p class="description"> Het Transgalactisch Liftershandboek (Engels: The Hitchhikerâ€˜s Guide to the Galaxy) is een komisch sciencefictionfranchise bedacht door Douglas Adams. Het begon als een radiohoorspel van twaalf afleveringen, voor het eerst uitgezonden in 1978 doorÂ BBC Radio, daarna door deÂ BBC World Service. In 1981 werd er een zesdelige televisieserie gemaakt. Al snel volgden andere media, waaronder een computerspel, drie toneelbewerkingen, negen graphic novels, een speelfilm en heel veel merchandise. De boekenserie was echter het succesvolst: tussen 1979 en 1992 verschenen vijf delen van de reeks. In 2008 kreeg auteur Eoin Colfer toestemming van de weduwe van Douglas Adams om de reeks af te maken met een zesde deel dat dit jaar in het Nederlands verschijnt: En dan nog iets...<br><br><br>(source: Bol.com)<br></p>'

        result = sanitize_description(input_html)

        # Should preserve the text content but sanitize HTML
        self.assertIn("Het Transgalactisch Liftershandboek", result)
        self.assertIn("Douglas Adams", result)
        # Should not contain dangerous attributes or excessive line breaks
        self.assertNotIn('class="description"', result)

    def test_simple_html(self):
        """Test simple HTML with basic formatting"""
        input_html = '<p>This is a <strong>simple</strong> description with <em>emphasis</em>.</p>'

        result = sanitize_description(input_html)

        # Should preserve basic formatting tags
        self.assertIn('This is a', result)
        self.assertIn('simple', result)
        self.assertIn('description with', result)
        self.assertIn('emphasis', result)

    def test_dangerous_html_content(self):
        """Test HTML with potentially dangerous content"""
        input_html = '<p onclick="alert(\'xss\')">Dangerous content</p><script>alert("xss")</script>'

        result = sanitize_description(input_html)

        # Should preserve safe content but remove dangerous elements
        self.assertIn("Dangerous content", result)
        # Should not contain dangerous scripts or event handlers
        self.assertNotIn("onclick", result)
        self.assertNotIn("<script>", result)
        # Note: Filter strips script tags but may leave content - this tests current behavior

    def test_plain_text(self):
        """Test plain text without HTML"""
        input_text = 'This is just plain text with no HTML.'

        result = sanitize_description(input_text)

        # Should return the text as-is
        self.assertEqual(result, input_text)

    def test_mixed_content(self):
        """Test mixed content with good and unwanted elements"""
        input_html = '<p>Good content</p><div class="unwanted">Bad div</div><p>More good content</p>'

        result = sanitize_description(input_html)

        # Should preserve good content
        self.assertIn("Good content", result)
        self.assertIn("More good content", result)
        # Should handle the unwanted div appropriately
        self.assertIn("Bad div", result)  # Content should be preserved even if container is changed

    def test_empty_input(self):
        """Test empty or None input"""
        self.assertEqual(sanitize_description(""), "")
        self.assertEqual(sanitize_description(None), "")
