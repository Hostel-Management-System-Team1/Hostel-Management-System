"""Dashboard panels, contributed by each module.

A module's ``dashboard.py`` decorates a function with ``@provider``; it receives the signed-in
user and returns a list of panels (usually empty for roles the module does not serve). Panels
are built with ``table_panel`` or ``facts_panel`` and drawn by templates/_panel.html. Modules
are imported from their AppConfig.ready().
"""

from django.utils.text import slugify

_providers = []


def provider(function):
    _providers.append(function)
    return function


def panels_for(user):
    panels = []
    for function in _providers:
        panels.extend(function(user) or [])
    for panel in panels:
        panel["id"] = "p-" + slugify(panel["title"])
    return panels


def cell(value):
    """A table cell: plain text, or (text, badge name) for a coloured status badge."""
    if isinstance(value, tuple):
        return {"text": value[0], "badge": value[1]}
    return {"text": value, "badge": None}


def table_panel(title, columns, rows, *, link=None, empty, alert=False):
    """rows is a list of (url or None, [cell, ...]); the first cell links to the url."""
    built = [
        {
            "url": url,
            "cells": [dict(cell(value), label=column) for column, value in zip(columns, values)],
        }
        for url, values in rows
    ]
    return {
        "title": title,
        "columns": columns,
        "rows": built,
        "link": link,
        "empty": empty,
        "alert": alert and bool(built),
    }


def facts_panel(title, facts, *, link=None, note=""):
    return {"title": title, "facts": facts, "link": link, "note": note, "empty": {}}


def empty(icon, title, text, action=None):
    return {"icon": icon, "title": title, "text": text, "action": action}
