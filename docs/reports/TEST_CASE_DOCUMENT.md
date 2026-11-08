# Test Case Document (updated after Sprint 2)

| Item | Detail |
|---|---|
| **Project** | Hostel Management System (HMS), Team 1 |
| **Build validated** | `main` at 9f65069 plus the changes in this pull request |
| **Dates** | Cases executed 2 November 2026 (QA register); full automated suite and reports re-run 8 November 2026 |
| **Environment** | Fedora 42, PostgreSQL 16, Django 5.2.18, `DJANGO_DEBUG=false` (the CI configuration) |
| **Prepared by** | Vignesh Nunna (PES2UG24CS582) |
| **QA lead review** | Vaishnavi Goyal (PES2UG24CS571) |

This is the Test Plan's list of cases (section 15), brought up to date with what was built. For each case it gives the scenario, the **expected result as it stands now**, the result, what changed from Test Plan v1.0 and the automated test that repeats it. Changes that come from a difference between a planning document and the product are explained in `DEVIATIONS.md`; the row numbers are in the System Validation Report.

- Test Plan v1.0 listed 30 cases. One more, **TC-OPS-AVAIL**, is added for HMS-NF-002 (availability), which the plan had left as "operations evidence".
- Status values: PASS, PARTIAL (the control works but the evidence the plan asked for is not available), NOT RUN.
- Re-run on 8 November 2026: all 376 automated tests pass. Cases whose evidence is manual (load test, drill, accessibility audit) were executed on 2 November and are recorded in `docs/qa/`.

## Test cases

| Test ID | Requirement | Scenario (steps) | Expected result (updated) | Status | Changed from Test Plan v1.0 | Automated test |
|---|---|---|---|---|---|---|
| TC-ADM-01 | HMS-F-001 | Submit a valid admission application, then a second for the same enrolment and session. | Valid submission gets HMS-2026-NNNNN; the duplicate is refused with a message naming the first (page and API 409). | PASS | As planned. | admissions.tests.SubmitApplicationTests, ApplyViewTests, ApplicationApiTests |
| TC-ALL-01 | HMS-F-002 | Allocate an approved applicant while vacant beds exist. | Only vacant, in-service beds matching gender, block and room type are offered; ranking (merit, seniority, first come) is followed. | PASS | — | admissions.test_allocation.AutomaticAllocationTests, RankingTests, ManualAllocationTests |
| TC-ALL-02 | HMS-F-003 | Warden transfers a resident to another bed. | Old bed vacant and new bed occupied in one transaction; reason, warden and time are audited. | PASS | As planned. | admissions.test_transfer.TransferServiceTests, TransferViewTests; audit.tests.WhatIsLoggedTests |
| TC-FEE-01 | HMS-F-010 | Allocate a bed; change the fee structure afterwards. | Invoice total equals the sum of its fee heads and does not change when fees change later. | PASS | As planned. | fees.tests.InvoiceGenerationTests |
| TC-FEE-02 | HMS-F-011 | Send success, failed, cancelled, abandoned, tampered and unsigned gateway callbacks. | Success marks the invoice Paid; the rest leave it Unpaid; tampered or unsigned callbacks are refused. | PASS | Callback is HMAC-signed and sent by the bundled mock gateway, not a provider sandbox. | fees.tests.PaymentFlowTests, FeesApiTests |
| TC-FEE-03 | HMS-F-012 | Pay an invoice and download the receipt. | Receipt RCT-YYYY-NNNNNN and a PDF are available in the same request (within 30 s). | PASS | As planned. | fees.tests.ReceiptTests |
| TC-FEE-04 | HMS-F-013 | Run the overdue job the day after the due date. | Unpaid invoice becomes Overdue; one reminder to the resident with the guardian in BCC. | PASS | Reminder is email only; failed sends are retried. Guardian is copied in BCC. | fees.tests.OverdueInvoiceTests |
| TC-GATE-01 | HMS-F-020 | Post a reader event; record a manual exit and entry on the Gate log; repeat an event. | A timestamped IN/OUT record is created each time; a repeated event is ignored. | PASS | Reader events arrive over a keyed HTTP API; the manual path is the Gate log page. No vendor SDK and no browser-side buffer. | gate.tests.GateMovementServiceTests, GateAPITests; test_acceptance.test_tc_gate_01 |
| TC-OUT-01 | HMS-F-021 | Resident requests an outpass; warden approves or rejects; guard records return. | Pending → Approved/Rejected; guardian emailed on approval and on return, not on rejection. | PASS | Guardian is notified by email. | test_acceptance.test_tc_out_01_* ; gate.tests.OutpassAndAttendanceTests |
| TC-GATE-02 | HMS-F-022 | Leave a resident out 31 minutes past curfew and run the alert job. | One alert, the wardens are emailed, and the alert shows on the warden's dashboard. | PASS | Alert is an email plus a dashboard panel, not a push; the 5-minute bound depends on the schedule. | test_acceptance.test_tc_gate_02; gate.tests.CurfewAlertTests |
| TC-ATT-01 | HMS-F-023 | Generate the night register for a date. | Room-by-room list with Present / On leave / Absent from gate and outpass records. | PASS | As planned. | test_acceptance.test_tc_att_01; gate.tests.OutpassAndAttendanceTests |
| TC-MESS-01 | HMS-F-030 | Mess manager publishes, edits, removes and copies meals; resident opens Meals. | A published meal is on the residents' page immediately. | PASS | Each meal is published on its own date and can be edited, removed and copied to next week; no versioned weekly menu. | test_acceptance.test_tc_mess_01 |
| TC-MESS-02 | HMS-F-031 | Skip a meal inside 24 hours and outside it; undo; bill a month. | Late skip refused; undo allowed until 24 h before; bill = ₹50 × meals not skipped, once per ended month. | PASS | Opt-out is per meal (24 hours ahead) and can be undone; bill = ₹50 × meals not skipped, ended months only. | test_acceptance.test_tc_mess_02_* |
| TC-CMP-01 | HMS-F-040 | Resident reports a Maintenance problem with a photo; try a photo over 5 MB. | Ticket #N with priority High; the large photo is refused; the complaint is in the warden's queue. | PASS | As planned. | test_acceptance.test_tc_cmp_01_* |
| TC-CMP-02 | HMS-F-041 | Move a complaint Open → In progress → Resolved → Closed. | Closing requires the resident's confirmation; closing an unresolved one is refused. | PASS | As planned. | test_acceptance.test_tc_cmp_02; test_screens.ComplaintScreenTests |
| TC-CMP-03 | HMS-F-042 | Leave High and Medium complaints unresolved past the SLA. | Escalation after 48 h / 96 h, every administrator emailed, entry in the audit log. | PASS | The 48 h and 96 h SLAs are fixed in code; escalation emails every Hostel Administrator. | complaints.tests.ComplaintSLATests |
| TC-VIS-01 | HMS-F-050 | Register visitors inside and outside visiting hours; warden overrides. | Out-of-hours entry refused; override needs a reason, which is audited; exit time recorded. | PASS | Relationship goes in the purpose of visit; the ID number is not encrypted at rest. | test_acceptance.test_tc_vis_01; visitors.tests; test_screens.VisitorScreenTests |
| TC-RPT-01 | HMS-F-060 | Open the management reports; export PDF and XLSX. | Figures reconcile with the records; both files open. | PASS | Shows the current state; no period picker. | test_acceptance.test_tc_rpt_01; reporting.tests.ReportingExportTests |
| TC-INV-01 | HMS-F-061 | Administrator deletes a room with an occupied bed; lowers capacity below beds in use. | Both are refused. | PASS | As planned. | admissions.test_allocation.RoomInventoryTests |
| TC-VAC-01 | HMS-F-062 | Vacate with incomplete and complete clearances. | Bed released only after all three clearances and paid invoices; refund = deposit − dues − damages; a negative result is payable. | PASS | Damage beyond the deposit is shown as payable and raised as an invoice (defect D-24). | admissions.test_vacating.VacatingServiceTests |
| TC-PERF-01 | HMS-NF-001 | Load test the resident portal with 200 concurrent users and 2,000 records. | 95th percentile ≤ 2 s. | PARTIAL | Run on a developer laptop with Waitress. | docs/performance/performance_test_summary.txt |
| TC-OPS-AVAIL | HMS-NF-002 | Monitor uptime over a month. | At least 99.5% available. | NOT RUN | Not run; needs a month of operation. | — |
| TC-OPS-01 | HMS-NF-003 | Back up the database and restore it into a fresh one. | Restore within 4 h and data loss within 24 h; data identical; audit chain verifies. | PASS | Drill timed on the development machine: backup 0.9 s, restore 0.7 s. | audit.test_backup_database; manual drill |
| TC-UX-01 | HMS-NF-004 | Audit every page for WCAG 2.1 AA, at 360 px and by keyboard; trial an untrained warden. | 0 violations; 80% of a 10-user trial complete allocation unaided in 5 min. | PARTIAL | axe-core audit in Chrome; the 10-user trial was not held. | manual audit (axe-core 4.x, Chrome) |
| TC-OPS-02 | HMS-NF-005 | Run the retention report and the anonymisation job. | Records older than 5 years are listed; their personal data is blanked and the records stay retrievable. | PASS | Anonymisation is the `anonymise_old_records` command, dry run by default (defect D-25). | test_acceptance.test_tc_ops_02_* |
| TC-SEC-01 | HMS-SR-001 | Inspect the TLS configuration. | No connection below TLS 1.2 and no weak ciphers. | PARTIAL | Settings enforced and tested; the TLS 1.2 minimum is set in the nginx example; no live scan. | test_security.TlsSettingsTests |
| TC-SEC-02 | HMS-SR-002 | Request every restricted URL as every other role; idle for 15 minutes; reuse a logged-out session. | 403 for other roles; idle session and logged-out session are rejected. | PASS | As planned. | accounts.test_rbac.AccessMatrixTests; accounts.test_auth.SessionTests |
| TC-SEC-03 | HMS-SR-003 | Inspect password storage; sign in as warden and administrator. | Non-reversible salted Argon2 hashes; the second step is mandatory. | PASS | As planned. | accounts.test_auth.PasswordStorageTests, MFATests |
| TC-SEC-04 | HMS-SR-004 | Perform privileged actions; try to edit or delete audit rows. | Actor, action, time, target and outcome recorded; entries cannot be changed. | PASS | The database itself refuses UPDATE and DELETE on the audit table; a hash chain detects tampering. | audit.tests |
| TC-SEC-05 | HMS-SR-005 | Post card data to the gateway page; inspect the database and logs. | No card number, CVV or bank credential is stored. | PASS | As planned. | fees.tests.NoCardDataTests |
| TC-SEC-06 | HMS-SR-006 | Run SQL-injection and stored-markup input on every page. | No injection or XSS finding; queries are parameterised. | PARTIAL | Hand-written injection and stored-markup tests on every page; no ZAP run. | test_security.InputHandlingTests, QueryStyleTests, ContentSecurityPolicyCompatibilityTests |

## What changed and why

| Kind of change | Cases | Reason |
|---|---|---|
| Mock or simplified external system (payment gateway, mail, gate reader) | TC-FEE-02, TC-FEE-04, TC-GATE-01, TC-GATE-02, TC-OUT-01 | No merchant account, SMS gateway or reader hardware for a course project (`DEVIATIONS.md` 3, 4, 7, 8, 9, 15) |
| Behaviour refined during the sprints | TC-MESS-01, TC-MESS-02, TC-CMP-03, TC-VIS-01, TC-RPT-01 | Per-meal rather than per-day mess, fixed SLAs, current-state reports (`DEVIATIONS.md` 10 to 13) |
| Defect fixes that changed expected results | TC-VAC-01, TC-OPS-02 | D-24 (shortfall payable), D-25 (anonymisation job) |
| Evidence the project cannot produce | TC-PERF-01, TC-OPS-AVAIL, TC-OPS-01, TC-UX-01, TC-SEC-01, TC-SEC-06 | Needs a production-like server, a month of uptime, ten users or an external scanner (`DEVIATIONS.md` 14, 17) |
| Extra detail | TC-SEC-04 | The database refuses UPDATE and DELETE, beyond "cannot be edited through the application" |
