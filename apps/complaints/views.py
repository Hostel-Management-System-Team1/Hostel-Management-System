
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from .forms import ComplaintForm
from .models import Complaint


@login_required
@role_required("RESIDENT")
def submit_complaint(request):
    if request.method == "POST":
        form = ComplaintForm(request.POST, request.FILES)

        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.created_by = request.user
            complaint.save()

            messages.success(request, "Complaint submitted successfully.")
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
    )

    return render(
        request,
        "complaints/my_complaints.html",
        {"complaints": complaints},
    )


@login_required
@role_required("WARDEN", "ADMINISTRATOR")
def manage_complaints(request):
    complaints = Complaint.objects.select_related(
        "created_by", "assigned_to"
    ).all()

    maintenance_staff = User.objects.filter(
        role="MAINTENANCE_STAFF"
    )

    return render(
        request,
        "complaints/manage_complaints.html",
        {
            "complaints": complaints,
            "maintenance_staff": maintenance_staff,
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
