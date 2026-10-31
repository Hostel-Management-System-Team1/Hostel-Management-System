"""Sidebar navigation per role (SRS 2.3)."""

from django.urls import reverse
from django.utils.text import slugify

from apps.accounts.models import User

R = User.Role

ISSUES_URL = (
    "https://github.com/Hostel-Management-System-Team1/"
    "Hostel-Management-System/issues"
)
SPRINT_DATES = {1: "19–23 Oct", 2: "26–30 Oct"}


def item(label, icon, url_name=None, sprint=None, hint="", issue=None):
    return {
        "label": label,
        "icon": icon,
        "url_name": url_name,
        "sprint": sprint,
        "hint": hint,
        "issue": issue,
        "issue_url": f"{ISSUES_URL}/{issue}" if issue else None,
        "sprint_dates": SPRINT_DATES.get(sprint, ""),
        "slug": slugify(label),
    }


DASHBOARD = item("Dashboard", "bi-grid-1x2", "home")

NAV = {
    R.RESIDENT: [
        ("Overview", [
            item("Home", "bi-house", "home"),
        ]),
        ("My hostel", [
            item(
                "Room application",
                "bi-file-earmark-text",
                "admissions:my_application",
                hint="Apply for a room",
            ),
            item(
                "Fees & receipts",
                "bi-receipt",
                "fees:invoice_list",
                hint="Invoices, payment and receipts",
            ),
            item(
                "My Vacating",
                "bi-box-arrow-right",
                "admissions:my_vacating",
                hint="Request hostel vacating and track clearances",
            ),
            item(
                "Outpass",
                "bi-box-arrow-up-right",
                "gate:outpasses",
                sprint=2,
                hint="Leave the hostel overnight",
                issue=9,
            ),
            item(
                "Meals",
                "bi-cup-hot",
                "mess:home",
                hint="Menu and meal opt-outs",
                issue=10,
            ),
        ]),
        ("Support", [
            item(
                "My complaints",
                "bi-tools",
                sprint=2,
                hint="Plumbing, electrical, Wi-Fi",
                issue=11,
            ),
        ]),
    ],

    R.WARDEN: [
        ("Overview", [DASHBOARD]),
        ("Residents", [
            item(
                "Applications",
                "bi-inbox",
                "admissions:application_list",
                hint="Review and allocate beds",
            ),
            item(
                "Rooms",
                "bi-door-closed",
                "admissions:room_list",
                hint="Occupancy by room",
            ),
            item(
                "Residents",
                "bi-people",
                "admissions:resident_list",
                hint="Rooms and transfers",
            ),
            item(
                "Vacating Requests",
                "bi-door-open",
                "admissions:vacating_list",
                hint="Review no-dues clearances and complete vacating",
            ),
            item(
                "Outpasses",
                "bi-box-arrow-up-right",
                "gate:warden_outpasses",
                sprint=2,
                hint="Approve or reject requests",
                issue=9,
            ),
            item(
                "Night attendance",
                "bi-moon",
                "gate:attendance",
                sprint=2,
                hint="Daily register per room",
                issue=9,
            ),
        ]),
        ("Operations", [
            item(
                "Complaints",
                "bi-tools",
                sprint=2,
                hint="Assign and track",
                issue=11,
            ),
            item(
                "Gate log",
                "bi-door-open",
                sprint=2,
                hint="Entries, exits and curfew",
                issue=8,
            ),
            item(
                "Visitors",
                "bi-person-badge",
                sprint=2,
                hint="Visiting-hour overrides",
                issue=12,
            ),
            item(
                "Reports",
                "bi-bar-chart",
                "reporting:dashboard",
                hint="Occupancy, dues, complaints",
            ),
        ]),
    ],

    R.SECURITY_GUARD: [
        ("Overview", [DASHBOARD]),
        ("Gate", [
            item(
                "Gate log",
                "bi-door-open",
                sprint=2,
                hint="Record entry and exit",
                issue=8,
            ),
            item(
                "Visitors",
                "bi-person-badge",
                sprint=2,
                hint="Register visitors",
                issue=12,
            ),
            item(
                "Resident returns",
                "bi-box-arrow-in-left",
                "gate:returns",
                hint="Record residents returning from approved outpasses",
                issue=9,
            ),
        ]),
    ],

    R.MAINTENANCE_STAFF: [
        ("Overview", [DASHBOARD]),
        ("Work", [
            item(
                "Complaints",
                "bi-tools",
                sprint=2,
                hint="Complaints assigned to you",
                issue=11,
            ),
        ]),
    ],

    R.MESS_MANAGER: [
        ("Overview", [DASHBOARD]),
        ("Mess", [
            item(
                "Weekly menu",
                "bi-calendar-week",
                "mess:home",
                hint="Publish the menu",
                issue=10,
            ),
            item(
                "Opt-outs & bills",
                "bi-cup-hot",
                sprint=2,
                hint="Meal counts and monthly bills",
                issue=10,
            ),
        ]),
    ],
}


ADMIN_NAV = [
    ("Overview", [
        item("Dashboard", "bi-grid-1x2", "admin:index"),
    ]),
    ("Residents", [
        item(
            "Applications",
            "bi-inbox",
            "admin:admissions_application_changelist",
            hint="Look up applications",
        ),
        item(
            "Residents",
            "bi-people",
            "admin:admissions_allocation_changelist",
            hint="Who lives where",
        ),
        item(
            "Fees",
            "bi-receipt",
            "admin:fees_invoice_changelist",
            hint="Invoices and payments",
        ),
    ]),
    ("Operations", [
        item(
            "Complaints",
            "bi-tools",
            sprint=2,
            hint="Escalations and SLA",
            issue=11,
        ),
        item(
            "Mess",
            "bi-cup-hot",
            sprint=2,
            hint="Menu and billing",
            issue=10,
        ),
        item(
            "Visitors",
            "bi-person-badge",
            sprint=2,
            hint="Visitor records",
            issue=12,
        ),
    ]),
    ("Masters", [
        item(
            "Hostel blocks",
            "bi-buildings",
            "admin:admissions_block_changelist",
            hint="Blocks and the gender each is for",
        ),
        item(
            "Rooms & beds",
            "bi-door-closed",
            "admin:admissions_room_changelist",
            hint="Room inventory: floor, type, capacity, status",
        ),
        item(
            "Fee structure",
            "bi-cash-coin",
            "admin:fees_feehead_changelist",
            hint="What each room type is charged",
        ),
        item(
            "Allocation order",
            "bi-sort-numeric-down",
            "admin:admissions_allocationpolicy_changelist",
            hint="Merit, seniority or first come",
        ),
    ]),
    ("Administration", [
        item(
            "Users & roles",
            "bi-person-gear",
            "admin:accounts_user_changelist",
            hint="Accounts and roles",
        ),
        item(
            "Reports",
            "bi-bar-chart",
            "reporting:dashboard",
            hint="PDF and XLSX exports",
        ),
        item(
            "Audit log",
            "bi-journal-text",
            "admin:audit_auditentry_changelist",
            hint="Allocations, fees, approvals",
        ),
    ]),
]


def nav_for(user, current_path=None, admin=False):
    """Return navigation groups with resolved URLs and active states."""
    source = ADMIN_NAV if admin else NAV.get(user.role, NAV[R.RESIDENT])
    placeholder = "admin:hms_module" if admin else "module"
    home_url = reverse("admin:index") if admin else reverse("home")
    groups = []

    for label, items in source:
        resolved = []

        for entry in items:
            entry = dict(entry, group=label)

            if entry["url_name"]:
                entry["url"] = reverse(entry["url_name"])
            else:
                entry["url"] = reverse(placeholder, args=[entry["slug"]])

            if entry["url"] == home_url:
                entry["active"] = current_path == home_url
            else:
                entry["active"] = (
                    bool(current_path)
                    and current_path.startswith(entry["url"])
                )

            resolved.append(entry)

        groups.append((label, resolved))

    return groups


def find_item(user, slug, admin=False):
    """Return a matching not-yet-built navigation item, if any."""
    for _, items in nav_for(user, admin=admin):
        for entry in items:
            if (
                entry["slug"] == slug
                and not entry["url_name"]
                and entry.get("sprint")
            ):
                return entry
    return None


def initials(user):
    first = user.first_name.strip()
    last = user.last_name.strip()

    if first or last:
        return (first[:1] + last[:1]).upper() or first[:2].upper()

    return user.username[:2].upper()


def navigation(request):
    """Provide navigation groups and avatar initials for signed-in users."""
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {}

    context = {"user_initials": initials(user)}

    if user.is_staff and request.path.startswith(reverse("admin:index")):
        context["admin_nav"] = nav_for(user, request.path, admin=True)
    else:
        context["nav_groups"] = nav_for(user, request.path)

    return context
