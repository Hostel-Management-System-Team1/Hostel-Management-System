from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from . import services
from .forms import ApplicationForm, DecisionForm
from .models import Application

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


STATUS_TABS = [("SUBMITTED", "Waiting"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]


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
    applications = Application.objects.filter(status=status).select_related("preferred_block")
    return render(request, "admissions/application_list.html", {
        "tabs": tabs, "applications": applications, "status": status,
    })


@role_required(R.WARDEN)
def application_detail(request, pk):
    application = get_object_or_404(Application.objects.select_related("preferred_block"), pk=pk)
    return render(request, "admissions/application_detail.html", {
        "application": application, "decision_form": DecisionForm(),
    })


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
