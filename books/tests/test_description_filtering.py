#!/usr/bin/env python3
"""Test script for the description sanitization filter."""

import os
import sys
import django

from books.templatetags.custom_filters import sanitize_description

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


# Test cases
test_cases = [
    # Test case 1: HTML with class attributes (like the user's example)
    '<p class="description"> Het Transgalactisch Liftershandboek (Engels: The Hitchhikerâ€˜s Guide to the Galaxy) is een komisch sciencefictionfranchise bedacht door Douglas Adams. Het begon als een radiohoorspel van twaalf afleveringen, voor het eerst uitgezonden in 1978 doorÂ BBC Radio, daarna door deÂ BBC World Service. In 1981 werd er een zesdelige televisieserie gemaakt. Al snel volgden andere media, waaronder een computerspel, drie toneelbewerkingen, negen graphic novels, een speelfilm en heel veel merchandise. De boekenserie was echter het succesvolst: tussen 1979 en 1992 verschenen vijf delen van de reeks. In 2008 kreeg auteur Eoin Colfer toestemming van de weduwe van Douglas Adams om de reeks af te maken met een zesde deel dat dit jaar in het Nederlands verschijnt: En dan nog iets...<br><br><br>(source: Bol.com)<br></p>',

    # Test case 2: Simple HTML
    '<p>This is a <strong>simple</strong> description with <em>emphasis</em>.</p>',

    # Test case 3: HTML with dangerous content
    '<p onclick="alert(\'xss\')">Dangerous content</p><script>alert("xss")</script>',

    # Test case 4: Plain text
    'This is just plain text with no HTML.',

    # Test case 5: Mixed content
    '<p>Good content</p><div class="unwanted">Bad div</div><p>More good content</p>'
]

print("Testing sanitize_description filter:")
print("=" * 50)

for i, test_case in enumerate(test_cases, 1):
    print(f"\nTest case {i}:")
    print("Input:", repr(test_case))
    result = sanitize_description(test_case)
    print("Output:", repr(result))
    print("Rendered:", result)
    print("-" * 30)
