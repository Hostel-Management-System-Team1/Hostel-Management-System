"""Form helpers shared by every module."""


class BootstrapFormMixin:
    """Gives widgets Bootstrap classes and links errors and help text for screen readers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            kind = widget.input_type if hasattr(widget, "input_type") else ""
            if kind in {"checkbox", "radio"}:
                css = "form-check-input"
            elif kind == "select" or widget.__class__.__name__ in {"Select", "SelectMultiple"}:
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()
            if field.help_text:
                widget.attrs["aria-describedby"] = f"id_{self.add_prefix(name)}_help"

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["aria-invalid"] = "true"
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} is-invalid".strip()
                widget.attrs["aria-describedby"] = f"id_{self.add_prefix(name)}_err"
