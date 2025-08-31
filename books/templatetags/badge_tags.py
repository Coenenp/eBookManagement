"""
Reusable badge template tags to eliminate duplication
"""
from django import template

register = template.Library()


@register.simple_tag
def confidence_badge(confidence, size=""):
    """Generate confidence level badge with consistent styling"""
    if confidence is None:
        return ""

    confidence = float(confidence)
    size_class = f" badge-{size}" if size else ""

    if confidence >= 0.8:
        badge_class = "badge bg-success"
        level = "High"
    elif confidence >= 0.5:
        badge_class = "badge bg-warning text-dark"
        level = "Medium"
    else:
        badge_class = "badge bg-danger"
        level = "Low"

    percentage = int(confidence * 100)
    return f'<span class="{badge_class}{size_class}" title="{level} confidence: {percentage}%">{percentage}%</span>'


@register.simple_tag
def status_badge(status_type, value=None, text=None, title=None):
    """Generate status badges with consistent styling"""
    badges = {
        'reviewed': {
            True: ('badge bg-success text-white', '✅ Reviewed'),
            False: ('badge bg-warning text-dark', '⚠️ Not Reviewed')
        },
        'needs_review': {
            True: ('badge bg-warning text-dark', '⚠️ Needs Review'),
            False: ('badge bg-success', '✅ Reviewed')
        },
        'duplicate': {
            True: ('badge bg-danger', '🔄 Duplicate'),
            False: ('badge bg-success', '✅ Unique')
        },
        'placeholder': {
            True: ('badge bg-info', '📄 Placeholder'),
            False: ('badge bg-success', '📚 Real File')
        },
        'active': {
            True: ('badge bg-success', 'Active'),
            False: ('badge bg-secondary', 'Inactive')
        },
        'final': ('badge bg-primary', 'Final'),
        'selected': ('badge bg-primary', 'Selected'),
        'new': ('badge bg-success', 'New'),
        'primary_source': ('badge bg-primary', 'Primary Source'),
        'alternate_source': ('badge bg-light text-dark', 'Alternate Source'),
        'original_scan': ('badge bg-secondary', 'Original Scan')
    }

    if status_type in ['reviewed', 'needs_review', 'duplicate', 'placeholder', 'active']:
        if value is None:
            return ""
        badge_class, default_text = badges[status_type][value]
        display_text = text or default_text
        title_attr = f' title="{title}"' if title else ""
        return f'<span class="{badge_class}"{title_attr}>{display_text}</span>'

    elif status_type in badges:
        badge_class, default_text = badges[status_type]
        display_text = text or default_text
        title_attr = f' title="{title}"' if title else ""
        return f'<span class="{badge_class}"{title_attr}>{display_text}</span>'

    return ""


@register.simple_tag
def metadata_source_badge(source_name, is_final=False, confidence=None):
    """Generate metadata source badges with confidence indicators"""
    if is_final:
        return '<span class="badge bg-primary ms-1">Final</span>'

    # Determine badge style based on source name
    source_styles = {
        'opf': 'badge bg-secondary',
        'filename': 'badge bg-info',
        'external': 'badge bg-warning text-dark',
        'manual': 'badge bg-success'
    }

    badge_class = source_styles.get(source_name.lower(), 'badge bg-light text-dark')

    if confidence is not None:
        confidence_text = f" ({int(float(confidence) * 100)}%)"
    else:
        confidence_text = ""

    return f'<span class="{badge_class}">{source_name}{confidence_text}</span>'


@register.simple_tag
def legend_badges():
    """Generate the confidence level legend"""
    return '''
    <div class="d-flex flex-wrap gap-2 align-items-center">
        <small class="text-muted me-2">Confidence Levels:</small>
        <span class="badge bg-success">High (≥0.8)</span>
        <span class="badge bg-warning text-dark">Medium (0.5-0.8)</span>
        <span class="badge bg-danger">Low (<0.5)</span>
        <span class="badge bg-primary">Primary Source</span>
        <span class="badge bg-light text-dark">Alternate Source</span>
        <span class="badge bg-secondary">Original Scan</span>
    </div>
    '''


@register.simple_tag
def field_badge(field_name, field_id=None):
    """Generate field-specific badges for forms"""
    badge_id = f'id="{field_id}_badge"' if field_id else ""
    return f'<span class="badge bg-primary" {badge_id}>Final</span>'
