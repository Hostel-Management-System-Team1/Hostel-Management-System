# Test Summary Report — Sprint 2 (issue #18)

Executed 2026-11-02 against `main` plus the Sprint 2 finish-up changes, on PostgreSQL 16 with `DJANGO_DEBUG=false` (the CI configuration). The register with per-case evidence is [`HMS_QA_Test_Execution_Register.xlsx`](HMS_QA_Test_Execution_Register.xlsx); the full automated run is [`test-run-2026-11-02.txt`](test-run-2026-11-02.txt).

## Result

| Status | Cases |
|---|---|
| PASS | 26 |
| PARTIAL | 4 |
| NOT RUN | 1 |

- **Automated suite:** 337 tests, all passing, including one acceptance test per Sprint 2 Test Plan case (`hms/test_acceptance.py`), driven through the pages each role uses.
- **Defects:** 25 found during execution, all fixed and retested (below).
- **Exit criteria:** every functional case passes. The remaining non-functional items need a production-like server or a user trial (see *Open items*).

## Test cases

| Test case | Status | Evidence | Automated tests |
|---|---|---|---|
| TC-ADM-01 | PASS | Valid application gets HMS-2026-NNNNN; a duplicate for the same enrolment/session is refused with a message naming the first (page and API 409). | admissions.tests.SubmitApplicationTests, ApplyViewTests, ApplicationApiTests |
| TC-ALL-01 | PASS | Only vacant, in-service beds in a block for the applicant's gender and requested type are offered; ranking (merit/seniority/first come) followed by Allocate all. | admissions.test_allocation.AutomaticAllocationTests, RankingTests, ManualAllocationTests |
| TC-ALL-02 | PASS | Transfer frees the old bed and fills the new one in one transaction; reason, warden and time are kept and audited. | admissions.test_transfer.TransferServiceTests, TransferViewTests; audit.tests.WhatIsLoggedTests |
| TC-INV-01 | PASS | Admin hides Delete for a room with an occupied bed; capacity cannot drop below beds in use. | admissions.test_allocation.RoomInventoryTests |
| TC-FEE-01 | PASS | Invoice raised on allocation from the fee structure; total equals the sum of fee heads; later fee changes do not alter it. | fees.tests.InvoiceGenerationTests |
| TC-FEE-02 | PASS | Signed success callback marks Paid; failed, cancelled and abandoned payments leave Unpaid; tampered or unsigned callbacks refused. | fees.tests.PaymentFlowTests, FeesApiTests |
| TC-FEE-03 | PASS | Receipt RCT-YYYY-NNNNNN issued on success with a downloadable PDF, generated in the same request. | fees.tests.ReceiptTests |
| TC-FEE-04 | PASS | Unpaid invoice turns Overdue the day after its due date; one reminder to resident with guardian in BCC; failed send retried. | fees.tests.OverdueInvoiceTests |
| TC-GATE-01 | PASS | Reader events (RFID/biometric, keyed device API) and the guard's manual Gate log both create timestamped IN/OUT records; duplicates ignored. | gate.tests.GateMovementServiceTests, GateAPITests; test_acceptance.test_tc_gate_01 |
| TC-OUT-01 | PASS | Pending → Approved/Rejected through the pages; guardian emailed on approval and on return; no email on rejection. | test_acceptance.test_tc_out_01_* ; gate.tests.OutpassAndAttendanceTests |
| TC-GATE-02 | PASS | Resident out 31 min after curfew raises one alert, emails the wardens and shows on the warden dashboard. Timing depends on the 5-minute schedule (DEVIATIONS 9). | test_acceptance.test_tc_gate_02; gate.tests.CurfewAlertTests |
| TC-ATT-01 | PASS | Register generated per night, room by room, Present / On leave / Absent from gate and outpass records. | test_acceptance.test_tc_att_01; gate.tests.OutpassAndAttendanceTests |
| TC-MESS-01 | PASS | Meal published from the week planner is on the residents' Meals page immediately; meals can be edited, removed, copied to next week, and meals served recorded. | test_acceptance.test_tc_mess_01 |
| TC-MESS-02 | PASS | Opt-out under 24 h refused, and can be undone until then; bill = ₹50 × published meals not skipped, only for residents with a bed, only for ended months, never twice. Per-meal rather than per-day (DEVIATIONS 10). | test_acceptance.test_tc_mess_02_* |
| TC-CMP-01 | PASS | Complaint gets ticket #N, priority from category (Maintenance = High), optional photo; over 5 MB refused; appears in the warden's queue. | test_acceptance.test_tc_cmp_01_* |
| TC-CMP-02 | PASS | Open → In progress (assigned) → Resolved (maintenance) → Closed (resident confirms); closing an unresolved complaint is refused. | test_acceptance.test_tc_cmp_02; test_screens.ComplaintScreenTests |
| TC-CMP-03 | PASS | High escalates after 48 h, Medium after 96 h; every Hostel Administrator emailed; escalation time and audit entry recorded (after fix D-03). | complaints.tests.ComplaintSLATests |
| TC-VIS-01 | PASS | Out-of-hours entry refused; warden override without reason refused, with reason allowed and audited; exit recorded with a timestamp. ID number not encrypted (DEVIATIONS 12). | test_acceptance.test_tc_vis_01; visitors.tests; test_screens.VisitorScreenTests |
| TC-RPT-01 | PASS | Occupancy, dues and complaint figures reconcile with the records; XLSX opens in openpyxl; PDF opens in the browser. Current state only, no period picker (DEVIATIONS 13). | test_acceptance.test_tc_rpt_01; reporting.tests.ReportingExportTests |
| TC-VAC-01 | PASS | Bed released only after all three clearances and paid invoices; refund = deposit − dues − damages. Damage beyond the deposit is shown as payable and raised as an invoice to the resident (after fix D-24). | admissions.test_vacating.VacatingServiceTests |
| TC-PERF-01 | PARTIAL | Locust, 2,000 seeded residents: p95 1.6 s, 0 failures (docs/performance). Run on a developer laptop, not a production-like server (DEVIATIONS 14). | docs/performance/performance_test_summary.txt |
| TC-OPS-AVAIL | NOT RUN | Uptime script exists (deploy/windows/check_uptime.ps1); a month of operation is needed for a 99.5% figure. | — |
| TC-OPS-01 | PASS | Drill on 2 Nov: backup_database 0.9 s, pg_restore into a fresh database 0.7 s; users, allocations, invoices and audit rows identical; verify_audit passes on the restored copy. Nightly schedule gives RPO ≤ 24 h. | audit.test_backup_database; manual drill |
| TC-OPS-02 | PASS | retention_report lists records older than 5 years; anonymise_old_records --apply blanks the personal data of residents who left over 5 years ago, old visitors and outpass contacts, and keeps the records so they can still be retrieved; dry run by default; scheduled monthly (after fixes D-07, D-08, D-25). | test_acceptance.test_tc_ops_02_* |
| TC-UX-01 | PARTIAL | axe-core WCAG 2.1 A/AA audit of 33 pages across 5 roles: 0 violations. Every page checked at 360 px; skip link and keyboard focus present. No 10-user trial held. | manual audit (axe-core 4.x, Chrome) |
| TC-SEC-01 | PARTIAL | HTTPS redirect, HSTS and secure cookies enforced outside development; nginx example allows TLS 1.2+ only. No live TLS scan (no deployed server). | test_security.TlsSettingsTests |
| TC-SEC-02 | PASS | Every restricted URL refuses every other role with 403; idle session expires at 15 min; a logged-out session cookie is rejected. | accounts.test_rbac.AccessMatrixTests; accounts.test_auth.SessionTests |
| TC-SEC-03 | PASS | Passwords stored as salted Argon2; Warden and Administrator held at the TOTP step until verified. | accounts.test_auth.PasswordStorageTests, MFATests |
| TC-SEC-04 | PASS | Actor, action, time, target and outcome recorded; no edit/delete in the app; database refuses UPDATE/DELETE; hash chain detects tampering. | audit.tests |
| TC-SEC-05 | PASS | No card number, CVV or bank credential field exists; card data posted to the gateway page is not stored. | fees.tests.NoCardDataTests |
| TC-SEC-06 | PARTIAL | SQL injection and stored-markup tests pass on every page; CSP forbids inline script; queries parameterised. No OWASP ZAP scan run. | test_security.InputHandlingTests, QueryStyleTests, ContentSecurityPolicyCompatibilityTests |

## Defects found and retested

| ID | Case | Severity | Defect | Fix | Retest |
|---|---|---|---|---|---|
| D-01 | TC-CMP-02 | High | Maintenance staff got HTTP 403 on Complaints, their only page | View opens to maintenance staff, showing complaints assigned to them | PASS – ComplaintScreenTests |
| D-02 | TC-VIS-01 | High | Warden had no way to reach a visitor to approve out-of-hours entry | Visitor list open to the warden with an Allow out of hours action | PASS – test_tc_vis_01 |
| D-03 | TC-CMP-03 | High | SLA escalation emailed nobody (mail_admins with no ADMINS configured) | Emails every active Hostel Administrator; audit entry complaint.escalated | PASS – ComplaintSLATests |
| D-04 | TC-MESS-02 | High | Monthly mess bills raised for residents without a bed | Only residents who held a bed during the month are billed | PASS – test_tc_mess_02_bill_counts_only… |
| D-05 | TC-MESS-02 | Medium | The month in progress could be billed, charging meals not yet served | Only ended months can be billed; the form defaults to last month | PASS – test_tc_mess_02_a_month_still_running… |
| D-06 | TC-MESS-02 | Low | ₹0 mess invoices raised for residents with no meals | No invoice when no meals were eaten | PASS |
| D-07 | TC-OPS-02 | High | retention_report crashed: python-dateutil not installed | Uses the standard library only | PASS – test_tc_ops_02 |
| D-08 | TC-OPS-02 | Medium | retention_report skipped gate and visitor records, saying their tables did not exist | Counts gate movements, outpasses and visitors too | PASS – test_tc_ops_02 |
| D-09 | TC-ADM-01 | Medium | Resident's application timeline showed “Rejected” once a bed was allocated | Timeline shows Approved → Bed allocated | PASS – visual check |
| D-10 | TC-UX-01 | High | Mess, complaints and visitor pages had no portal layout or styling | Rebuilt on the portal layout | PASS – visual check, axe audit |
| D-11 | TC-GATE-01 | High | Gate entry/exit had no screen; ~10 sidebar links opened “Coming in Sprint 2” | Gate log page; every sidebar link opens its page | PASS – NavigationCompleteTests, GateLogTests |
| D-12 | TC-RPT-01 | Medium | Administrator's Reports opened in the resident portal layout | Reports open inside the admin site | PASS – AdminReportsTests |
| D-13 | TC-UX-01 | Low | Admin header squeezed to 41 px; list cells touching the card edge; filter values broken mid-word | Header 60 px, 20 px cell inset, wider filter column | PASS – visual check |
| D-14 | TC-UX-01 | Medium | Warden's sidebar cut off Sign out on a 900 px-high screen | Sidebar scrolls | PASS – visual check |
| D-15 | TC-UX-01 | Medium | At 360 px, three-column figures and the complaint assign form ran off screen | Two columns and wrapping form on phones | PASS – visual check |
| D-16 | TC-VAC-01 | Low | Vacating form still offered while a request was open | Shows the open request instead | PASS – visual check |
| D-17 | TC-CMP-01 | Low | No ticket number shown for a new complaint | “Complaint #N submitted”; numbers shown in lists | PASS – test_tc_cmp_01 |
| D-18 | TC-MESS-02 | Low | A skipped meal could not be un-skipped | Undo until 24 hours before the meal; week shown as a day × meal grid | PASS – test_tc_mess_02_opt_out… |
| D-19 | TC-RPT-01 | Low | PDF reports downloaded instead of opening, with a cramped layout | PDF opens in a new tab; A4 landscape with title, row count, page numbers | PASS – test_tc_rpt_01 |
| D-20 | TC-SEC-04 | Medium | Admin lists allowed bulk delete of complaints, visitors, menu items and gate records | Bulk delete removed site-wide; visitor, outpass and attendance records are view-only | PASS – test_lists_have_no_bulk_actions… |
| D-21 | TC-UX-01 | Low | Admin edit pages showed related-record icons, calendar pop-ups and uneven inputs | Browser date/time pickers, one input style, icons removed | PASS – visual check |
| D-22 | TC-ADM-01 | Low | Year of study was a free number box; applicants typed the calendar year | Dropdown of 1st–6th year | PASS – visual check |
| D-23 | TC-RPT-01 | Medium | Meals served could not be recorded anywhere but the admin, so the mess activity report stayed empty; meals could not be edited or removed | Week planner: add, edit, remove and copy meals; record meals served on past meals | PASS – test_tc_mess_01_manager_plans_the_week |
| D-24 | TC-VAC-01 | Medium | Damage beyond the deposit showed a ₹0 refund instead of an amount payable | Shortfall shown as payable and raised as an invoice to the resident | PASS – test_damage_beyond_the_deposit_is_shown_as_payable_and_billed |
| D-25 | TC-OPS-02 | Medium | No job anonymised personal data after the 5-year retention period | anonymise_old_records command (dry run by default, --apply to change) | PASS – test_tc_ops_02_old_personal_data_is_anonymised… |

## Open items reported to the QA lead

| Case | What is outstanding | Recorded in |
|---|---|---|
| TC-PERF-01 | Load test repeated on a production-like server | DEVIATIONS 14 |
| TC-OPS-AVAIL | A month of uptime data | DEVIATIONS 14 |
| TC-UX-01 | 10-user allocation trial | — |
| TC-SEC-01 | Live TLS scan of the deployed server | — |
| TC-SEC-06 | OWASP ZAP scan | — |

## How to repeat

```bash
python manage.py test                      # whole suite
python manage.py test hms.test_acceptance  # Test Plan acceptance cases
python manage.py backup_database --output-dir /tmp/hms-backups   # TC-OPS-01, then pg_restore into a new database
python manage.py retention_report --years 5                       # TC-OPS-02
```
