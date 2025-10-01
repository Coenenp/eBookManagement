"""
Template tags for language management.
"""
from django import template
from books.utils.language_manager import LanguageManager

register = template.Library()


@register.inclusion_tag('books/snippets/language_select.html')
def language_select(field_name='language', selected_value=None, include_empty=True, empty_label='Select language',
                    css_class='form-control', required=False, all_languages=False, all_label='All Languages'):
    """
    Render a language select dropdown.

    Usage:
        {% language_select field_name='language' selected_value=book.language %}
        {% language_select field_name='language' include_empty=False %}
        {% language_select field_name='filter_language' all_languages=True %}
    """
    if all_languages:
        choices = LanguageManager.get_language_choices_with_all(all_label)
    elif include_empty:
        choices = LanguageManager.get_language_choices_with_empty(empty_label)
    else:
        choices = LanguageManager.get_language_choices()

    return {
        'field_name': field_name,
        'choices': choices,
        'selected_value': selected_value or '',
        'css_class': css_class,
        'required': required,
    }


@register.inclusion_tag('books/snippets/language_options.html')
def language_options(selected_value=None, include_empty=True, empty_label='Select language', all_languages=False, all_label='All Languages'):
    """
    Render language option tags for use inside an existing select element.

    Usage:
        <select name="language" class="form-control">
            {% language_options selected_value=book.language %}
        </select>
    """
    if all_languages:
        choices = LanguageManager.get_language_choices_with_all(all_label)
    elif include_empty:
        choices = LanguageManager.get_language_choices_with_empty(empty_label)
    else:
        choices = LanguageManager.get_language_choices()

    return {
        'choices': choices,
        'selected_value': selected_value or '',
    }


@register.simple_tag
def language_name(code):
    """
    Get the display name for a language code.

    Usage:
        {{ book.language|language_name }}
    """
    return LanguageManager.get_language_name(code)


@register.simple_tag
def language_choices():
    """
    Get the language choices list.

    Usage:
        {% language_choices as choices %}
        {% for code, name in choices %}
            <option value="{{ code }}">{{ name }}</option>
        {% endfor %}
    """
    return LanguageManager.get_language_choices()


@register.simple_tag
def language_choices_with_empty(empty_label='Select language'):
    """
    Get language choices with an empty option.

    Usage:
        {% language_choices_with_empty as choices %}
    """
    return LanguageManager.get_language_choices_with_empty(empty_label)


@register.simple_tag
def language_choices_with_all(all_label='All Languages'):
    """
    Get language choices with an 'all' option.

    Usage:
        {% language_choices_with_all as choices %}
    """
    return LanguageManager.get_language_choices_with_all(all_label)
