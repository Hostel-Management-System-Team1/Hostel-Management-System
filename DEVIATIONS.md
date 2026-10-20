# Deviations from the SRS, SAD and Test Plan

Every place the implementation differs from the submitted documents is recorded
here, with the reason. These are explained during the final demo.

| # | Document & section | What the document says | What we built instead | Reason | Sprint |
|---|---|---|---|---|---|

| 1 | SRS 2.5 and 3.3, SAD 3.6 — student identity from the institutional ERP | A read-only HTTPS/JSON lookup against the ERP checks the enrolment number | A stub adapter (`apps/admissions/erp.py`) that only checks the enrolment number's format; the applicant types their own details. A real client plugs in through `HMS_ERP_ADAPTER` | No ERP sandbox exists for the course project | 1 |
| 2 | SAD 3.4 — room-inventory master belongs to the Reporting & Admin Service | Room, block and bed masters (HMS-F-061) sit in Reporting & Admin | They live in the Admission & Allocation app (`apps/admissions`) next to the allocation that uses them; the administrator maintains them in the admin site | Allocation and the inventory change in one transaction; a separate app would only add cross-app imports | 1 |
| 3 | SRS 2.5 and 3.3, SAD 3.6 — payments through a PCI-DSS compliant gateway | A real provider's hosted page, with signed callbacks and refunds | A bundled mock gateway (`apps/fees/gateway.py`): a stand-in hosted page that asks for no card or bank details and sends the same HMAC-signed callback a provider would. The HMS stores only the method name and the gateway reference. Refunds are recorded in the vacating workflow, not sent to a provider | No merchant account or provider sandbox for a course project | 1 |
| 4 | SAD 3.6 — retry with exponential backoff and a dead-letter queue for gateway calls | Gateway and notification failures are retried with backoff | A gateway outage is reported to the resident at once (API 502) and the invoice stays Unpaid; the resident retries. Notification retries are built in Sprint 2 | The mock gateway cannot fail on its own, so retry logic for it would be untestable | 1 |
