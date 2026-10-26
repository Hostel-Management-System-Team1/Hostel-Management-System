
import csv
from functools import wraps
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.accounts.models import User
from apps.admissions.models import Bed, Room
from apps.complaints.models import Complaint
from apps.fees.models import Invoice
from apps.mess.models import MessActivity


def report_access_required(view_func):
    """Restrict reports to wardens and administrators."""

    @login_required
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if request.user.role not in (
            User.Role.WARDEN,
            User.Role.ADMINISTRATOR,
        ):
            raise PermissionDenied(
                "Only wardens and administrators can access reports."
            )
        return view_func(request, *args, **kwargs)

    return wrapped_view


def occupancy_rows():
    rows = [[
        "Block", "Room", "Floor", "Room type", "Room status",
        "Occupied beds", "Total beds",
    ]]
    rooms = Room.objects.select_related(
        "block"
    ).prefetch_related("beds")

    for room in rooms.iterator(chunk_size=100):
        occupied = sum(
            bed.status == Bed.Status.OCCUPIED
            for bed in room.beds.all()
        )
        rows.append([
            room.block.name,
            room.number,
            room.floor,
            room.get_room_type_display(),
            room.get_status_display(),
            occupied,
            room.bed_capacity,
        ])
    return rows


def dues_rows():
    rows = [[
        "Invoice", "Resident", "Description", "Due date", "Status", "Amount",
    ]]
    invoices = Invoice.objects.exclude(
        status=Invoice.Status.PAID
    ).select_related("resident")

    for invoice in invoices.iterator():
        rows.append([
            invoice.number,
            invoice.resident.get_username(),
            invoice.description,
            str(invoice.due_date),
            invoice.get_status_display(),
            str(invoice.total),
        ])
    return rows


def complaint_rows():
    rows = [[
        "Title", "Category", "Status", "Created by",
        "Created at", "Age in days",
    ]]
    complaints = Complaint.objects.select_related("created_by").order_by(
        "status", "created_at"
    )

    for complaint in complaints.iterator():
        rows.append([
            complaint.title,
            complaint.get_category_display(),
            complaint.get_status_display(),
            complaint.created_by.get_username(),
            timezone.localtime(complaint.created_at).strftime(
                "%Y-%m-%d %H:%M"
            ),
            complaint.age_days,
        ])
    return rows


def mess_rows():
    rows = [[
        "Activity date", "Meal type", "Meals served", "Notes", "Recorded by",
    ]]
    activities = MessActivity.objects.select_related(
        "recorded_by"
    ).order_by("-activity_date", "meal_type")

    for activity in activities.iterator():
        rows.append([
            str(activity.activity_date),
            activity.get_meal_type_display(),
            activity.meals_served,
            activity.notes,
            activity.recorded_by.get_username(),
        ])
    return rows


def csv_response(filename, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    csv.writer(response).writerows(rows)
    return response


def xlsx_response(filename, rows, sheet_name):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name

    for row in rows:
        sheet.append(row)

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    for cell in sheet[1]:
        cell.font = cell.font.copy(bold=True)

    for column_cells in sheet.columns:
        width = max(
            len(str(cell.value or "")) for cell in column_cells
        )
        sheet.column_dimensions[
            column_cells[0].column_letter
        ].width = min(width + 2, 40)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response


def pdf_response(filename, title, rows):
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(title, styles["Title"]),
        Paragraph(
            "Generated: "
            + timezone.localtime().strftime("%Y-%m-%d %H:%M"),
            styles["Normal"],
        ),
        Spacer(1, 12),
        Table(rows, repeatRows=1),
    ]

    elements[-1].setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24476b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#edf2f7"),
        ]),
    ]))
    document.build(elements)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response


@report_access_required
def reports_dashboard(request):
    total_beds = Bed.objects.count()
    occupied_beds = Bed.objects.filter(
        status=Bed.Status.OCCUPIED
    ).count()

    unpaid_invoices = Invoice.objects.exclude(
        status=Invoice.Status.PAID
    )
    outstanding_total = (
        unpaid_invoices.aggregate(total=Sum("total"))["total"] or 0
    )

    complaints = Complaint.objects.select_related(
        "created_by"
    ).order_by("status", "created_at")
    mess_activities = MessActivity.objects.select_related(
        "recorded_by"
    ).order_by("-activity_date", "meal_type")

    context = {
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "vacant_beds": Bed.objects.filter(
            status=Bed.Status.VACANT
        ).count(),
        "occupancy_percent": round(
            occupied_beds / total_beds * 100, 1
        ) if total_beds else 0,
        "unpaid_invoices": unpaid_invoices.select_related("resident"),
        "outstanding_total": outstanding_total,
        "complaints": complaints,
        "open_complaints": complaints.filter(
            status__in=[
                Complaint.Status.OPEN,
                Complaint.Status.IN_PROGRESS,
            ]
        ).count(),
        "mess_activities": mess_activities,
        "total_meals_served": (
            mess_activities.aggregate(total=Sum("meals_served"))["total"]
            or 0
        ),
    }
    return render(request, "reporting/reports.html", context)


@report_access_required
def export_dues_csv(request):
    return csv_response("outstanding-dues.csv", dues_rows())


@report_access_required
def export_occupancy_csv(request):
    return csv_response("hostel-occupancy.csv", occupancy_rows())


@report_access_required
def export_complaints_csv(request):
    return csv_response("complaint-ageing.csv", complaint_rows())


@report_access_required
def export_mess_csv(request):
    return csv_response("mess-activities.csv", mess_rows())


@report_access_required
def export_dues_xlsx(request):
    return xlsx_response(
        "outstanding-dues.xlsx", dues_rows(), "Outstanding Dues"
    )


@report_access_required
def export_occupancy_xlsx(request):
    return xlsx_response(
        "hostel-occupancy.xlsx", occupancy_rows(), "Hostel Occupancy"
    )


@report_access_required
def export_complaints_xlsx(request):
    return xlsx_response(
        "complaint-ageing.xlsx", complaint_rows(), "Complaint Ageing"
    )


@report_access_required
def export_mess_xlsx(request):
    return xlsx_response(
        "mess-activities.xlsx", mess_rows(), "Mess Activities"
    )


@report_access_required
def export_dues_pdf(request):
    return pdf_response(
        "outstanding-dues.pdf", "Outstanding Fees and Dues", dues_rows()
    )


@report_access_required
def export_occupancy_pdf(request):
    return pdf_response(
        "hostel-occupancy.pdf", "Hostel Occupancy Report", occupancy_rows()
    )


@report_access_required
def export_complaints_pdf(request):
    return pdf_response(
        "complaint-ageing.pdf", "Complaint Ageing Report", complaint_rows()
    )


@report_access_required
def export_mess_pdf(request):
    return pdf_response(
        "mess-activities.pdf", "Mess Activities Report", mess_rows()
    )
