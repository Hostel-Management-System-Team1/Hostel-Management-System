# Deviations from the SRS, SAD and Test Plan

Every place the implementation differs from the submitted documents is recorded
here, with the reason. These are explained during the final demo.

| # | Document & section | What the document says | What we built instead | Reason | Sprint |
|---|---|---|---|---|---|

| 1 | SRS 2.5 and 3.3, SAD 3.6 — student identity from the institutional ERP | A read-only HTTPS/JSON lookup against the ERP checks the enrolment number | A stub adapter (`apps/admissions/erp.py`) that only checks the enrolment number's format; the applicant types their own details. A real client plugs in through `HMS_ERP_ADAPTER` | No ERP sandbox exists for the course project | 1 |
| 2 | SAD 3.4 — room-inventory master belongs to the Reporting & Admin Service | Room, block and bed masters (HMS-F-061) sit in Reporting & Admin | They live in the Admission & Allocation app (`apps/admissions`) next to the allocation that uses them; the administrator maintains them in the admin site | Allocation and the inventory change in one transaction; a separate app would only add cross-app imports | 1 |
