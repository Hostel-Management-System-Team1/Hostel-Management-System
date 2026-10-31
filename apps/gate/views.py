
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from . import services
from .models import NightAttendance, OutpassRequest


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

    requests = OutpassRequest.objects.filter(
        resident=request.user
    ).order_by("-requested_at")

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
                f"Attendance generated: {result['created']} created, "
                f"{result['updated']} updated.",
            )
            return redirect(
                f"{request.path}?date={attendance_date.isoformat()}"
            )
        except ValueError:
            messages.error(request, "Please select a valid attendance date.")

    records = NightAttendance.objects.filter(
        attendance_date=selected_date
    ).select_related("resident", "room__block").order_by(
        "room__block__name",
        "room__number",
        "resident__username",
    )

    return render(
        request,
        "gate/attendance.html",
        {
            "records": records,
            "selected_date": selected_date,
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

    approved_outpasses = OutpassRequest.objects.filter(
        status=OutpassRequest.Status.APPROVED,
        returned_at__isnull=True,
    ).select_related(
        "resident",
        "allocation__bed__room__block",
    ).order_by("expected_return_at")

    return render(
        request,
        "gate/returns.html",
        {"outpasses": approved_outpasses},
    )
