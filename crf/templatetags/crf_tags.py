from decimal import Decimal

from django import template
from django.utils.html import format_html

from crf import spec

register = template.Library()

STATE = {
    'complete': ('success', 'Complete'),
    'incomplete': ('danger', 'Items missing'),
    'not_started': ('secondary', 'Not started'),
    'calculated': ('info', 'Calculated'),
}


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag
def state_badge(state, short=False, label=''):
    color, text = STATE.get(state, ('secondary', state))
    return format_html('<span class="badge text-bg-{}" title="{}">{}</span>', color, text, label if short else text)


@register.filter
def show(value, field_name=None):
    """Display a stored value, with choice labels for coded fields."""
    if value in (None, ''):
        return '—'
    if field_name and field_name in spec.FIELD_BY_NAME:
        _s, f = spec.FIELD_BY_NAME[field_name]
        if f.choices and f.type == 'select_one':
            return spec.choice_label(f.choices, value)
    if isinstance(value, Decimal):
        return f'{value.normalize():f}'
    if isinstance(value, float):
        return f'{value:g}'
    return value


@register.filter
def range_text(r):
    return f'{r[0]:g}–{r[1]:g}' if r else ''


@register.filter
def pct_class(pct):
    if pct >= 100:
        return 'success'
    if pct >= 60:
        return 'warning'
    return 'danger'


@register.filter
def tojson(value):
    import json
    return json.dumps(value, default=str)


@register.filter
def split_pairs(value):
    """"a:A,b:B" -> [('a', 'A'), ('b', 'B')], for small option lists in templates."""
    return [tuple(item.split(':', 1)) for item in value.split(',')]
