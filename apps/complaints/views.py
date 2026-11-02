from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import role_required
from apps.audit import service as audit

from .forms import ComplaintForm
from .models import Complaint

STATUS_TABS = [
    ("open", "Open", [Complaint.Status.OPEN, Complaint.Status.IN_PROGRESS]),
    ("resolved", "Resolved", [Complaint.Status.RESOLVED]),
    ("closed", "Closed", [Complaint.Status.CLOSED]),
]


@login_required
@role_required("RESIDENT")
def submit_complaint(request):
    if request.method == "POST":
        form = ComplaintForm(request.POST, request.FILES)

        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.created_by = request.user
            complaint.save()
            audit.record(
                "complaint.submitted",
                target=complaint,
                detail={"category": complaint.category, "priority": complaint.priority},
            )

            messages.success(
                request,
                f"Complaint #{complaint.pk} submitted. The warden will assign it to maintenance.",
            )
            return redirect("complaints:my_complaints")
    else:
        form = ComplaintForm()

    return render(
        request,
        "complaints/submit_complaint.html",
        {"form": form},
    )


@login_required
@role_required("RESIDENT")
def my_complaints(request):
    complaints = Complaint.objects.filter(
        created_by=request.user
    ).select_related("assigned_to").order_by("-created_at")

    return render(
        request,
        "complaints/my_complaints.html",
        {"complaints": complaints},
    )


@login_required
@role_required("WARDEN", "ADMINISTRATOR", "MAINTENANCE_STAFF")
def manage_complaints(request):
    """Wardens see every complaint; maintenance staff see the ones assigned to them."""
    complaints = Complaint.objects.select_related("created_by", "assigned_to")
    if request.user.role == User.Role.MAINTENANCE_STAFF:
        complaints = complaints.filter(assigned_to=request.user)

    selected = request.GET.get("status", "open")
    tabs = []
    for value, label, statuses in STATUS_TABS:
        tabs.append({
            "value": value,
            "label": label,
            "count": complaints.filter(status__in=statuses).count(),
            "active": value == selected,
        })
        if value == selected:
            shown = complaints.filter(status__in=statuses)
    if not any(tab["active"] for tab in tabs):
        tabs[0]["active"] = True
        shown = complaints.filter(status__in=STATUS_TABS[0][2])

    maintenance_staff = User.objects.filter(
        role="MAINTENANCE_STAFF", is_active=True
    )

    return render(
        request,
        "complaints/manage_complaints.html",
        {
            "complaints": shown.order_by("created_at"),
            "tabs": tabs,
            "maintenance_staff": maintenance_staff,
            "can_assign": request.user.role != User.Role.MAINTENANCE_STAFF,
        },
    )


@login_required
@role_required("WARDEN", "ADMINISTRATOR")
def assign_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, pk=complaint_id)

    if request.method == "POST":
        staff_id = request.POST.get("assigned_to")

        staff = get_object_or_404(
            User,
            pk=staff_id,
            role="MAINTENANCE_STAFF",
        )

        complaint.assigned_to = staff
        complaint.status = Complaint.Status.IN_PROGRESS
        complaint.save()
        audit.record(
            "complaint.assigned", target=complaint, detail={"assigned_to": staff.username}
        )

        messages.success(request, "Complaint assigned successfully.")

    return redirect("complaints:manage_complaints")


@login_required
@role_required("MAINTENANCE_STAFF", "WARDEN", "ADMINISTRATOR")
def update_complaint_status(request, complaint_id):
    complaint = get_object_or_404(Complaint, pk=complaint_id)

    if request.method == "POST":
        new_status = request.POST.get("status")

        allowed_statuses = {
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.RESOLVED,
        }

        if new_status in allowed_statuses:
            if (
                request.user.role == "MAINTENANCE_STAFF"
                and complaint.assigned_to_id != request.user.id
            ):
                messages.error(
                    request,
                    "You can only update complaints assigned to you.",
                )
            else:
                complaint.status = new_status

                if new_status == Complaint.Status.RESOLVED:
                    complaint.resolved_at = timezone.now()
                    complaint.resolution_confirmed = False

                complaint.save()
                audit.record(
                    "complaint.status_changed", target=complaint, detail={"status": new_status}
                )
                messages.success(request, "Complaint status updated.")

    return redirect("complaints:manage_complaints")


@login_required
@role_required("RESIDENT")
def confirm_resolution(request, complaint_id):
    complaint = get_object_or_404(
        Complaint,
        pk=complaint_id,
        created_by=request.user,
    )

    if request.method == "POST":
        if complaint.status == Complaint.Status.RESOLVED:
            complaint.resolution_confirmed = True
            complaint.status = Complaint.Status.CLOSED
            complaint.save()
            audit.record("complaint.closed", target=complaint)

            messages.success(
                request,
                "Thank you. The complaint has been closed.",
            )
        else:
            messages.error(
                request,
                "You can confirm only a resolved complaint.",
            )

    return redirect("complaints:my_complaints")
