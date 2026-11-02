from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import role_required
from apps.audit import service as audit

from .forms import VisitorRegistrationForm
from .models import VisitingHours, Visitor


@role_required(User.Role.SECURITY_GUARD)
def visitor_register(request):
    if request.method == "POST":
        form = VisitorRegistrationForm(request.POST)
        if form.is_valid():
            visitor = form.save(commit=False)
            visitor.registered_by = request.user
            visitor.save()
            audit.record("visitor.registered", target=visitor)
            messages.success(request, "Visitor registered successfully.")
            return redirect("visitors:list")
    else:
        form = VisitorRegistrationForm()

    return render(request, "visitors/register.html", {"form": form})


@role_required(User.Role.SECURITY_GUARD, User.Role.WARDEN)
def visitor_list(request):
    """The guard registers visitors and records entry and exit; the warden approves
    visits outside visiting hours from the same list (HMS-F-050, HMS-F-051)."""
    visitors = Visitor.objects.select_related(
        "resident", "registered_by", "overridden_by"
    )
    return render(request, "visitors/list.html", {
        "visitors": visitors,
        "hours": VisitingHours.objects.filter(is_active=True).first(),
        "within_hours": within_visiting_hours(),
        "is_guard": request.user.role == User.Role.SECURITY_GUARD,
        "inside": visitors.filter(status=Visitor.Status.INSIDE).count(),
        "waiting": visitors.filter(status=Visitor.Status.REGISTERED).count(),
    })


def within_visiting_hours():
    configuration = VisitingHours.objects.filter(is_active=True).first()
    if not configuration:
        return False

    current_time = timezone.localtime().time()
    return configuration.start_time <= current_time <= configuration.end_time


@role_required(User.Role.SECURITY_GUARD)
@require_POST
def visitor_entry(request, pk):
    visitor = get_object_or_404(Visitor, pk=pk)

    if visitor.entry_time:
        messages.error(request, "Visitor entry is already recorded.")
        return redirect("visitors:list")

    if visitor.exit_time:
        messages.error(request, "This visitor has already exited.")
        return redirect("visitors:list")

    if not within_visiting_hours() and not (
        visitor.overridden_by and visitor.override_reason
    ):
        messages.error(
            request,
            "Entry is outside permitted visiting hours. Warden approval is required.",
        )
        return redirect("visitors:list")

    visitor.entry_time = timezone.now()
    visitor.status = Visitor.Status.INSIDE
    visitor.save(update_fields=["entry_time", "status", "updated_at"])
    audit.record("visitor.entered", target=visitor)
    messages.success(request, "Visitor entry recorded.")

    return redirect("visitors:list")


@role_required(User.Role.SECURITY_GUARD)
@require_POST
def visitor_exit(request, pk):
    visitor = get_object_or_404(Visitor, pk=pk)

    if not visitor.entry_time or visitor.exit_time:
        messages.error(request, "A valid visitor entry must exist before exit.")
        return redirect("visitors:list")

    visitor.exit_time = timezone.now()
    visitor.status = Visitor.Status.EXITED
    visitor.save(update_fields=["exit_time", "status", "updated_at"])
    audit.record("visitor.exited", target=visitor)
    messages.success(request, "Visitor exit recorded.")

    return redirect("visitors:list")


@role_required(User.Role.WARDEN)
def visitor_override(request, pk):
    visitor = get_object_or_404(Visitor, pk=pk)

    if request.method == "GET":
        return render(request, "visitors/override.html", {"visitor": visitor})

    reason = request.POST.get("reason", "").strip()

    if not reason:
        messages.error(request, "A reason is required for the override.")
        return redirect("visitors:list")

    if visitor.entry_time or visitor.exit_time:
        messages.error(request, "Override is only available before visitor entry.")
        return redirect("visitors:list")

    visitor.override_reason = reason
    visitor.overridden_by = request.user
    visitor.save(update_fields=["override_reason", "overridden_by", "updated_at"])
    audit.record("visitor.hours_override", target=visitor, detail={"reason": reason[:200]})

    messages.success(request, "Warden override approved with reason.")
    return redirect("visitors:list")
