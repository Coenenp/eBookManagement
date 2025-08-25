from django import template

register = template.Library()


@register.inclusion_tag('books/confidence_meter.html')
def confidence_meter(confidence, source=None):
    if confidence is None:
        return {}

    # Use Bootstrap classes consistently
    css_class = (
        "bg-success" if confidence > 0.8 else
        "bg-warning text-dark" if confidence > 0.5 else
        "bg-danger"
    )

    width = max(0, min(100, round(confidence * 100)))  # clamp between 0 and 100

    return {
        "confidence": confidence,
        "css_class": css_class,
        "width": width,
        "source": source
    }
