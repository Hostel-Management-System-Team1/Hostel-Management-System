
from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    path("", views.reports_dashboard, name="dashboard"),

    path("export/dues.csv", views.export_dues_csv, name="export_dues"),
    path(
        "export/occupancy.csv",
        views.export_occupancy_csv,
        name="export_occupancy",
    ),
    path(
        "export/complaints.csv",
        views.export_complaints_csv,
        name="export_complaints",
    ),
    path("export/mess.csv", views.export_mess_csv, name="export_mess"),

    path("export/dues.xlsx", views.export_dues_xlsx, name="export_dues_xlsx"),
    path(
        "export/occupancy.xlsx",
        views.export_occupancy_xlsx,
        name="export_occupancy_xlsx",
    ),
    path(
        "export/complaints.xlsx",
        views.export_complaints_xlsx,
        name="export_complaints_xlsx",
    ),
    path("export/mess.xlsx", views.export_mess_xlsx, name="export_mess_xlsx"),

    path("export/dues.pdf", views.export_dues_pdf, name="export_dues_pdf"),
    path(
        "export/occupancy.pdf",
        views.export_occupancy_pdf,
        name="export_occupancy_pdf",
    ),
    path(
        "export/complaints.pdf",
        views.export_complaints_pdf,
        name="export_complaints_pdf",
    ),
    path("export/mess.pdf", views.export_mess_pdf, name="export_mess_pdf"),
]
