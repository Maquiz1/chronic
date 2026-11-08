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


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bootstrapify(self)
