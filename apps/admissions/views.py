from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from . import allocation as allocator
from . import services
from .forms import ApplicationForm, DecisionForm, TransferForm
from .models import Allocation, AllocationPolicy, Application, Bed, Block, Room

R = User.Role


@role_required(R.RESIDENT)
def my_application(request):
    """The resident's own application: the form until one is submitted, then its status."""
    application = Application.objects.filter(applicant=request.user).first()
    if application is None:
        return redirect("admissions:apply")
    return render(request, "admissions/application_status.html", {"application": application})


@role_required(R.RESIDENT)
def apply(request):
    if Application.objects.filter(applicant=request.user).exists():
        return redirect("admissions:my_application")
    form = ApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            application = services.submit_application(request.user, **form.cleaned_data)
        except services.DuplicateApplication as error:
            form.add_error("enrolment_number", str(error))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request, f"Application submitted. Your application number is "
                f"{application.application_number}."
            )
            return redirect("admissions:my_application")
    return render(request, "admissions/apply.html", {"form": form})


STATUS_TABS = [
    ("SUBMITTED", "Waiting for review"),
    ("APPROVED", "Approved, no bed yet"),
    ("ALLOCATED", "Bed allocated"),
    ("REJECTED", "Rejected"),
]


@role_required(R.WARDEN)
def application_list(request):
    status = request.GET.get("status", "SUBMITTED")
    if status not in dict(STATUS_TABS):
        status = "SUBMITTED"
    counts = dict(Application.objects.values_list("status").annotate(n=Count("id")))
    tabs = [
        {"value": value, "label": label, "count": counts.get(value, 0), "active": value == status}
        for value, label in STATUS_TABS
    ]
    if status == Application.Status.APPROVED:
        applications = allocator.ranked_waiting_applications()  # in allocation order
    else:
        applications = Application.objects.filter(status=status).select_related("preferred_block")
    return render(request, "admissions/application_list.html", {
        "tabs": tabs, "applications": applications, "status": status,
        "policy": AllocationPolicy.current(),
    })


@role_required(R.WARDEN)
def application_detail(request, pk):
    application = get_object_or_404(Application.objects.select_related("preferred_block"), pk=pk)
    context = {"application": application, "decision_form": DecisionForm()}
    if application.status == Application.Status.APPROVED:
        context["suggested"] = allocator.candidate_beds(application).first()
        context["eligible_beds"] = allocator.vacant_beds(application.gender).order_by(
            "room__block__name", "room__floor", "room__number", "label")
    elif application.status == Application.Status.ALLOCATED:
        context["allocation"] = application.allocation
    return render(request, "admissions/application_detail.html", context)


@role_required(R.WARDEN)
@require_POST
def application_decide(request, pk):
    application = get_object_or_404(Application, pk=pk)
    action = request.POST.get("action")
    if action not in {"approve", "reject"}:
        raise Http404("Unknown action")
    form = DecisionForm(request.POST)
    if form.is_valid():
        try:
            services.decide(application, request.user, action == "approve",
                            form.cleaned_data["note"])
        except services.DecisionError as error:
            messages.error(request, str(error))
        else:
            verb = "approved" if action == "approve" else "rejected"
            messages.success(request, f"Application {application.application_number} {verb}.")
    return redirect("admissions:application_detail", pk=pk)


@role_required(R.WARDEN)
@require_POST
def application_allocate(request, pk):
    """Allocate the suggested bed, or the one the warden picked."""
    application = get_object_or_404(Application, pk=pk)
    bed = None
    if request.POST.get("bed"):
        bed = get_object_or_404(Bed, pk=request.POST["bed"])
    try:
        allocation = allocator.allocate(application, request.user, bed=bed)
    except allocator.AllocationError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request, f"{application.full_name} is allocated {allocation.bed}."
        )
    return redirect("admissions:application_detail", pk=pk)


@role_required(R.WARDEN)
@require_POST
def allocate_all(request):
    allocations, skipped = allocator.allocate_all(request.user)
    if allocations:
        messages.success(request, f"{len(allocations)} applicants were allocated beds.")
    for application, reason in skipped:
        messages.warning(request, f"{application.full_name}: {reason}")
    if not allocations and not skipped:
        messages.info(request, "No approved applications are waiting for a bed.")
    return redirect(f"{reverse('admissions:application_list')}?status=APPROVED")


@role_required(R.WARDEN)
def room_list(request):
    """Occupancy by room, with who sleeps in each bed."""
    block_id = request.GET.get("block", "")
    rooms = Room.objects.select_related("block").prefetch_related(
        "beds", "beds__allocations__resident"
    )
    if block_id.isdigit():
        rooms = rooms.filter(block_id=block_id)
    rows = []
    for room in rooms:
        beds = list(room.beds.all())
        occupants = []
        for bed in beds:
            for allocation in bed.allocations.all():
                if allocation.status == Allocation.Status.ACTIVE:
                    occupants.append(allocation.resident.get_full_name()
                                     or allocation.resident.username)
        rows.append({
            "room": room,
            "beds": len(beds),
            "occupied": sum(b.status == Bed.Status.OCCUPIED for b in beds),
            "vacant": sum(b.status == Bed.Status.VACANT for b in beds),
            "occupants": occupants,
        })
    return render(request, "admissions/room_list.html", {
        "rows": rows, "blocks": Block.objects.all(), "block_id": block_id,
    })


@role_required(R.WARDEN)
def resident_list(request):
    """Everyone with a bed, for transfers and a look at who lives where."""
    allocations = Allocation.objects.filter(status=Allocation.Status.ACTIVE).select_related(
        "resident", "application", "bed__room__block")
    query = request.GET.get("q", "").strip()
    if query:
        allocations = allocations.filter(
            Q(resident__first_name__icontains=query) | Q(resident__last_name__icontains=query)
            | Q(resident__username__icontains=query)
            | Q(application__enrolment_number__icontains=query)
            | Q(bed__room__number__icontains=query))
    return render(request, "admissions/resident_list.html", {
        "allocations": allocations.order_by("bed__room__block__name", "bed__room__number",
                                            "bed__label"),
        "query": query,
    })


@role_required(R.WARDEN)
def resident_detail(request, pk):
    """One resident's bed, with the transfer form and the history of earlier moves."""
    allocation = get_object_or_404(
        Allocation.objects.select_related("resident", "application", "bed__room__block"),
        pk=pk, status=Allocation.Status.ACTIVE,
    )
    form = TransferForm(request.POST or None, allocation=allocation)
    if request.method == "POST" and form.is_valid():
        try:
            record = allocator.transfer(
                allocation, form.cleaned_data["bed"], form.cleaned_data["reason"], request.user)
        except allocator.TransferError as error:
            form.add_error(None, str(error))
        else:
            messages.success(
                request, f"{allocation.resident.get_full_name() or allocation.resident.username} "
                f"moved from {record.from_bed} to {record.to_bed}.")
            return redirect("admissions:resident_detail", pk=pk)
    transfers = allocation.transfers.select_related("from_bed__room__block",
                                                    "to_bed__room__block", "performed_by")
    return render(request, "admissions/resident_detail.html", {
        "allocation": allocation, "form": form, "transfers": transfers,
    })
