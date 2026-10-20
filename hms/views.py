from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from apps.accounts.forms import ProfileForm
from apps.accounts.models import User

from .dashboard import empty, panels_for, table_panel
from .navigation import find_item

R = User.Role

# Per-role dashboard: page title and the main panel. Until a module is built,
# its panel shows the design's empty state rather than placeholder numbers.
DESKS = {
    R.RESIDENT: {
        "title": None,  # the resident's own name
        "panel": "Your room",
        "empty_icon": "bi-door-closed",
        "empty_title": "No room allocated yet",
        "empty_text": "When the warden approves your application, your room, "
        "roommate and warden will show here.",
    },
    R.WARDEN: {
        "title": "Warden’s desk",
        "panel": "Pending applications",
        "empty_icon": "bi-inbox",
        "empty_title": "No applications waiting",
        "empty_text": "New hostel applications will appear here for review and bed allocation.",
    },
    R.SECURITY_GUARD: {
        "title": "Gate desk",
        "panel": "Recent movements",
        "empty_icon": "bi-door-open",
        "empty_title": "No gate movements yet",
        "empty_text": "Entries and exits recorded at the gate will appear here.",
    },
    R.MAINTENANCE_STAFF: {
        "title": "Maintenance desk",
        "panel": "Assigned to you",
        "empty_icon": "bi-tools",
        "empty_title": "No complaints assigned",
        "empty_text": "Complaints the warden assigns to you will appear here, oldest first.",
    },
    R.MESS_MANAGER: {
        "title": "Mess office",
        "panel": "This week’s menu",
        "empty_icon": "bi-cup-hot",
        "empty_title": "No menu published",
        "empty_text": "The weekly menu you publish will appear here and on every resident’s home.",
    },
}


def portal_view(view):
    """Login required; Hostel Administrators are sent to the admin site, their portal."""

    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return redirect("admin:index")
        return view(request, *args, **kwargs)

    return wrapper


@portal_view
def home(request):
    user = request.user
    desk = DESKS.get(user.role, DESKS[R.RESIDENT])
    panels = panels_for(user) or [
        table_panel(desk["panel"], [], [], empty=empty(
            desk["empty_icon"], desk["empty_title"], desk["empty_text"]))
    ]
    context = {
        "desk": desk,
        "panels": panels,
        "page_title": desk["title"] or user.get_full_name() or user.username,
    }
    return render(request, "home.html", context)


@portal_view
def module_page(request, slug):
    """Placeholder for a sidebar item whose screen is planned but not built yet.

    Only items in the user's own navigation resolve, so one role cannot open
    another role's pages (HMS-SR-002).
    """
    entry = find_item(request.user, slug)
    if entry is None:
        raise Http404("No such page")
    return render(request, "module.html", {"entry": entry})


@portal_view
def profile(request):
    """Let people keep their own name, email and phone up to date."""
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was saved.")
        return redirect("profile")
    return render(request, "profile.html", {"form": form})
