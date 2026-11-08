from django.contrib import messages
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import role_required
from apps.admissions.models import Allocation

from . import services
from .models import CurfewAlert, GateMovement, NightAttendance, OutpassRequest

R = User.Role


@role_required(R.SECURITY_GUARD, R.WARDEN)
def gate_log(request):
    """Gate log (HMS-F-020, HMS-F-022).

    The guard finds a resident and records an entry or exit by hand when the RFID or
    biometric reader is not used; the warden sees the same log and the curfew alerts.
    """
    is_guard = request.user.role == R.SECURITY_GUARD

    if request.method == "POST":
        if not is_guard:
            return redirect("gate:log")
        resident = get_object_or_404(User, pk=request.POST.get("resident"), role=R.RESIDENT)
        direction = request.POST.get("direction", "")
        try:
            services.record_movement(
                resident, direction, GateMovement.CaptureMethod.MANUAL, recorded_by=request.user
            )
        except services.InvalidGateMovement as error:
            messages.error(request, str(error))
        else:
            verb = "entry" if direction == GateMovement.Direction.IN else "exit"
            name = resident.get_full_name() or resident.username
            messages.success(request, f"Recorded the {verb} of {name}.")
        query = request.POST.get("q", "")
        return redirect(f"{request.path}?q={query}" if query else request.path)

    last_move = GateMovement.objects.filter(resident=OuterRef("resident")).order_by(
        "-occurred_at", "-pk"
    )
    residents = (
        Allocation.objects.filter(status=Allocation.Status.ACTIVE)
        .select_related("resident", "bed__room__block")
        .annotate(
            last_direction=Subquery(last_move.values("direction")[:1]),
            last_at=Subquery(last_move.values("occurred_at")[:1]),
        )
        .order_by("bed__room__block__name", "bed__room__number", "bed__label")
    )
    query = request.GET.get("q", "").strip()
    if query:
        residents = residents.filter(
            Q(resident__first_name__icontains=query)
            | Q(resident__last_name__icontains=query)
            | Q(resident__username__icontains=query)
            | Q(bed__room__number__icontains=query)
        )
    residents = list(residents)
    out_now = sum(1 for a in residents if a.last_direction == GateMovement.Direction.OUT)

    today = timezone.localdate()
    movements = GateMovement.objects.select_related("resident", "recorded_by")[:25]
    alerts = CurfewAlert.objects.select_related("resident", "block")[:10]

    return render(
        request,
        "gate/log.html",
        {
            "is_guard": is_guard,
            "residents": residents,
            "query": query,
            "out_now": out_now,
            "in_now": len(residents) - out_now,
            "moves_today": GateMovement.objects.filter(occurred_at__date=today).count(),
            "alerts_today": CurfewAlert.objects.filter(curfew_date=today).count(),
            "movements": movements,
            "alerts": alerts,
        },
    )


@role_required(User.Role.RESIDENT)
def outpass_page(request):
    if request.method == "POST":
        try:
            expected_return_at = timezone.datetime.fromisoformat(
                request.POST.get("expected_return_at", "")
            )
            if timezone.is_naive(expected_return_at):
                expected_return_at = timezone.make_aware(expected_return_at)

            services.submit_outpass(
                resident=request.user,
                destination=request.POST.get("destination", ""),
                contact_number=request.POST.get("contact_number", ""),
                expected_return_at=expected_return_at,
            )
            messages.success(request, "Your outpass request was submitted.")
            return redirect("gate:outpasses")
        except (services.OutpassError, ValueError) as error:
            messages.error(request, str(error))

    requests = OutpassRequest.objects.filter(resident=request.user).order_by("-requested_at")

    return render(
        request,
        "gate/outpasses.html",
        {"outpasses": requests},
    )


@role_required(User.Role.WARDEN)
def attendance_page(request):
    selected_date = request.GET.get(
        "date",
        timezone.localdate().isoformat(),
    )

    if request.method == "POST":
        try:
            attendance_date = timezone.datetime.strptime(
                request.POST.get("attendance_date", ""),
                "%Y-%m-%d",
            ).date()

            result = services.generate_night_attendance(attendance_date)
            messages.success(
                request,
                f"Attendance generated: {result['created']} created, {result['updated']} updated.",
            )
            return redirect(f"{request.path}?date={attendance_date.isoformat()}")
        except ValueError:
            messages.error(request, "Please select a valid attendance date.")

    records = (
        NightAttendance.objects.filter(attendance_date=selected_date)
        .select_related("resident", "room__block")
        .order_by(
            "room__block__name",
            "room__number",
            "resident__username",
        )
    )

    counts = {status: 0 for status in NightAttendance.Status.values}
    for record in records:
        counts[record.status] += 1

    return render(
        request,
        "gate/attendance.html",
        {
            "records": records,
            "selected_date": selected_date,
            "counts": counts,
        },
    )


@role_required(User.Role.WARDEN)
def warden_outpass_page(request):
    if request.method == "POST":
        try:
            outpass_id = int(request.POST.get("outpass_id", ""))
            decision = request.POST.get("decision", "")
            reason = request.POST.get("reason", "")

            services.decide_outpass(
                outpass_id=outpass_id,
                warden=request.user,
                decision=decision,
                reason=reason,
            )
            messages.success(request, "Outpass decision saved.")
        except (ValueError, services.OutpassError) as error:
            messages.error(request, str(error))
        except OutpassRequest.DoesNotExist:
            messages.error(request, "Outpass request not found.")

        return redirect("gate:warden_outpasses")

    requests = OutpassRequest.objects.select_related(
        "resident",
        "allocation__bed__room__block",
    ).order_by("status", "-requested_at")

    return render(
        request,
        "gate/warden_outpasses.html",
        {"outpasses": requests},
    )


@role_required(User.Role.SECURITY_GUARD)
def gate_returns_page(request):
    if request.method == "POST":
        try:
            outpass_id = int(request.POST.get("outpass_id", ""))
            services.record_outpass_return(
                outpass_id=outpass_id,
                guard=request.user,
            )
            messages.success(request, "Resident return recorded successfully.")
        except (ValueError, services.OutpassError) as error:
            messages.error(request, str(error))
        except OutpassRequest.DoesNotExist:
            messages.error(request, "Outpass request not found.")

        return redirect("gate:returns")

    approved_outpasses = (
        OutpassRequest.objects.filter(
            status=OutpassRequest.Status.APPROVED,
            returned_at__isnull=True,
        )
        .select_related(
            "resident",
            "allocation__bed__room__block",
        )
        .order_by("expected_return_at")
    )

    return render(
        request,
        "gate/returns.html",
        {"outpasses": approved_outpasses, "now": timezone.now()},
    )
