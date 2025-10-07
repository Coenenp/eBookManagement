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
        badge_class = "badge status-success"
        level = "High"
    elif confidence >= 0.5:
        badge_class = "badge status-warning"
        level = "Medium"
    else:
        badge_class = "badge status-danger"
        level = "Low"

    percentage = int(confidence * 100)
    return f'<span class="{badge_class}{size_class}" title="{level} confidence: {percentage}%">{percentage}%</span>'


@register.simple_tag
def status_badge(status_type, value=None, text=None, title=None):
    """Generate status badges with consistent styling"""
    badges = {
        'reviewed': {
            True: ('badge status-success', '✅ Reviewed'),
            False: ('badge status-warning', '⚠️ Not Reviewed')
        },
        'needs_review': {
            True: ('badge status-warning', '⚠️ Needs Review'),
            False: ('badge status-success', '✅ Reviewed')
        },
        'duplicate': {
            True: ('badge status-danger', '🔄 Duplicate'),
            False: ('badge status-success', '✅ Unique')
        },
        'placeholder': {
            True: ('badge status-info', '📄 Placeholder'),
            False: ('badge status-success', '📚 Real File')
        },
        'active': {
            True: ('badge status-success', 'Active'),
            False: ('badge status-neutral', 'Inactive')
        },
        'final': ('badge status-info', 'Final'),
        'selected': ('badge status-info', 'Selected'),
        'new': ('badge status-success', 'New'),
        'primary_source': ('badge status-info', 'Primary Source'),
        'alternate_source': ('badge status-neutral', 'Alternate Source'),
        'initial_scan': ('badge status-neutral', 'Initial Scan')
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
        'opf': 'badge status-neutral',
        'initial_scan': 'badge status-info',
        'external': 'badge status-warning',
        'manual': 'badge status-success'
    }

    badge_class = source_styles.get(source_name.lower(), 'badge status-neutral')

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
        <span class="badge status-success">High (≥0.8)</span>
        <span class="badge status-warning">Medium (0.5-0.8)</span>
        <span class="badge status-danger">Low (<0.5)</span>
        <span class="badge status-info">Primary Source</span>
        <span class="badge status-neutral">Alternate Source</span>
        <span class="badge status-neutral">Initial Scan</span>
    </div>
    '''


@register.simple_tag
def field_badge(field_name, field_id=None):
    """Generate field-specific badges for forms"""
    badge_id = f'id="{field_id}_badge"' if field_id else ""
    return f'<span class="badge bg-primary" {badge_id}>Final</span>'
