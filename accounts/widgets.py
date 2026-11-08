from django import forms


def bootstrapify(form):
    """Add Bootstrap classes to a form's widgets."""
    for field in form.fields.values():
        w = field.widget
        if isinstance(w, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
            continue
        if isinstance(w, forms.CheckboxInput):
            w.attrs.setdefault('class', 'form-check-input')
        elif isinstance(w, forms.Select):
            w.attrs.setdefault('class', 'form-select')
        else:
            w.attrs.setdefault('class', 'form-control')


def position_dropdown(form):
    """Show "position" as a drop-down of titles, keeping a stored title that is not (or no longer) in the list."""
    from .models import POSITIONS
    field = form.fields.get('position')
    if field is None:
        return
    choices = [('', '---------')] + [(p, p) for p in POSITIONS]
    current = getattr(getattr(form, 'instance', None), 'position', '') or ''
    if current and current not in POSITIONS:
        choices.append((current, current))
    form.fields['position'] = forms.ChoiceField(choices=choices, required=False, label=field.label,
                                                help_text=field.help_text)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        position_dropdown(self)
        bootstrapify(self)
