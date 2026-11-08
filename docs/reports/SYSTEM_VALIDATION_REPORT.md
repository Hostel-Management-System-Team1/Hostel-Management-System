# System Validation Report

| | |
|---|---|
| **Project** | Hostel Management System (HMS), Team 1 |
| **Build validated** | `main` at a9af58e plus the changes in this pull request |
| **Dates** | Cases executed 2 November 2026 (QA register); full automated suite and reports re-run 8 November 2026 |
| **Environment** | Fedora 42, PostgreSQL 16, Django 5.2.18, `DJANGO_DEBUG=false` (the CI configuration) |
| **Prepared by** | Vignesh Nunna (PES2UG24CS582) |
| **QA lead review** | Vaishnavi Goyal (PES2UG24CS571) |

This report answers one question: *does the running system do what the SRS asks, role by role?* It follows the Test Plan (sections 3, 5 and 15) and uses the same requirement and test-case IDs as the SRS traceability matrix.

## 1. Verdict

| Result | Cases |
|---|---|
| PASS | **26** |
| PARTIAL (works, but the Test Plan's evidence needs something we do not have) | **4** |
| NOT RUN | **1** |
| Total Test Plan cases | 31 |

- **All 20 functional requirements pass.** Each of the 20 has a Test Plan case, and every one of them passes, with documented deviations where the implementation differs from the SRS.
- **Security:** 4 of 6 pass outright. TC-SEC-01 (live TLS scan) and TC-SEC-06 (ZAP scan) are partial because they need a deployed server and an external tool; the controls themselves are tested.
- **Non-functional:** backup/restore and retention pass; performance and usability are partial; availability could not be measured in the time available (it needs a month of operation).
- **The automated suite behind these results:** 376 tests, 376 pass (see the Unit Test Report), 93% line-and-branch coverage (see the Code Coverage and Branch Coverage Reports).

## 2. How the system was validated

| Method | What it covered | Evidence |
|---|---|---|
| Automated acceptance tests | The Sprint 2 Test Plan cases (gate, outpass, curfew, attendance, mess, complaints, visitors, reports, retention), driven through the same pages and APIs each role uses (`hms/test_acceptance.py`, 17 tests) plus the module suites | `unit-test-run.txt` |
| Role walkthrough | All 6 roles on a seeded database with 11 accounts (resident, warden, guard, maintenance, mess manager, administrator), following a written checklist | Sprint 1 and Sprint 2 demo videos in `docs/demo/` |
| Accessibility audit | axe-core WCAG 2.1 A/AA on 33 pages across 5 roles, and every page at 360 px | `docs/qa/TEST_SUMMARY.md` (TC-UX-01) |
| Load test | Locust, 2,000 seeded residents, 200 concurrent users | `docs/performance/` |
| Backup / restore drill | `backup_database`, `pg_restore` into a fresh database, `verify_audit` | `docs/qa/TEST_SUMMARY.md` (TC-OPS-01) |
| Defect tracking | Each failure logged with severity, fixed, and retested (section 5) | `docs/qa/TEST_SUMMARY.md` |

## 3. Requirement-by-requirement result

"Dev." is the row in `DEVIATIONS.md` that explains a difference from the SRS, SAD or Test Plan.

| Requirement | Title | Test case | Result | Dev. | Evidence |
|---|---|---|---|---|---|
| HMS-F-001 | Submit admission application | TC-ADM-01 | **PASS** | — | Valid application gets HMS-2026-NNNNN; a duplicate for the same enrolment/session is refused with a message naming the first (page and API 409). |
| HMS-F-002 | Automatic bed allocation | TC-ALL-01 | **PASS** | — | Only vacant, in-service beds in a block for the applicant's gender and requested type are offered; ranking (merit/seniority/first come) followed by Allocate all. |
| HMS-F-003 | Room transfer by warden | TC-ALL-02 | **PASS** | — | Transfer frees the old bed and fills the new one in one transaction; reason, warden and time are kept and audited. |
| HMS-F-010 | Generate fee invoice | TC-FEE-01 | **PASS** | — | Invoice raised on allocation from the fee structure; total equals the sum of fee heads; later fee changes do not alter it. |
| HMS-F-011 | Online fee payment | TC-FEE-02 | **PASS** | 3 | Signed success callback marks Paid; failed, cancelled and abandoned payments leave Unpaid; tampered or unsigned callbacks refused. |
| HMS-F-012 | Receipt generation | TC-FEE-03 | **PASS** | — | Receipt RCT-YYYY-NNNNNN issued on success with a downloadable PDF, generated in the same request. |
| HMS-F-013 | Overdue flag and reminders | TC-FEE-04 | **PASS** | 4, 7 | Unpaid invoice turns Overdue the day after its due date; one reminder to resident with guardian in BCC; failed send retried. |
| HMS-F-020 | Gate entry-exit capture | TC-GATE-01 | **PASS** | 8, 15 | Reader events (RFID/biometric, keyed device API) and the guard's manual Gate log both create timestamped IN/OUT records; duplicates ignored. |
| HMS-F-021 | Outpass workflow and guardian notice | TC-OUT-01 | **PASS** | 7 | Pending → Approved/Rejected through the pages; guardian emailed on approval and on return; no email on rejection. |
| HMS-F-022 | Curfew violation alert | TC-GATE-02 | **PASS** | 9 | Resident out 31 min after curfew raises one alert, emails the wardens and shows on the warden dashboard. Timing depends on the 5-minute schedule (DEVIATIONS 9). |
| HMS-F-023 | Night-attendance register | TC-ATT-01 | **PASS** | — | Register generated per night, room by room, Present / On leave / Absent from gate and outpass records. |
| HMS-F-030 | Publish mess menu | TC-MESS-01 | **PASS** | 10 | Meal published from the week planner is on the residents' Meals page immediately; meals can be edited, removed, copied to next week, and meals served recorded. |
| HMS-F-031 | Mess opt-out and billing | TC-MESS-02 | **PASS** | 10 | Opt-out under 24 h refused, and can be undone until then; bill = ₹50 × published meals not skipped, only for residents with a bed, only for ended months, never twice. Per-meal rather than per-day (DEVIATIONS 10). |
| HMS-F-040 | Lodge complaint | TC-CMP-01 | **PASS** | — | Complaint gets ticket #N, priority from category (Maintenance = High), optional photo; over 5 MB refused; appears in the warden's queue. |
| HMS-F-041 | Complaint lifecycle | TC-CMP-02 | **PASS** | — | Open → In progress (assigned) → Resolved (maintenance) → Closed (resident confirms); closing an unresolved complaint is refused. |
| HMS-F-042 | SLA escalation | TC-CMP-03 | **PASS** | 11 | High escalates after 48 h, Medium after 96 h; every Hostel Administrator emailed; escalation time and audit entry recorded (after fix D-03). |
| HMS-F-050 | Visitor registration and hours | TC-VIS-01 | **PASS** | 12 | Out-of-hours entry refused; warden override without reason refused, with reason allowed and audited; exit recorded with a timestamp. ID number not encrypted (DEVIATIONS 12). |
| HMS-F-060 | Management reports | TC-RPT-01 | **PASS** | 13 | Occupancy, dues and complaint figures reconcile with the records; XLSX opens in openpyxl; PDF opens in the browser. Current state only, no period picker (DEVIATIONS 13). |
| HMS-F-061 | Room inventory master | TC-INV-01 | **PASS** | — | Admin hides Delete for a room with an occupied bed; capacity cannot drop below beds in use. |
| HMS-F-062 | No-dues clearance and refund | TC-VAC-01 | **PASS** | — | Bed released only after all three clearances and paid invoices; refund = deposit − dues − damages. Damage beyond the deposit is shown as payable and raised as an invoice to the resident (after fix D-24). |
| HMS-NF-001 | Response time and capacity | TC-PERF-01 | **PARTIAL** | 14 | Locust, 2,000 seeded residents: p95 1.6 s, 0 failures (docs/performance). Run on a developer laptop, not a production-like server (DEVIATIONS 14). |
| HMS-NF-002 | Availability 99.5% | TC-OPS-AVAIL | **NOT RUN** | 14 | Uptime script exists (deploy/windows/check_uptime.ps1); a month of operation is needed for a 99.5% figure. |
| HMS-NF-003 | Backup and recovery | TC-OPS-01 | **PASS** | 14 | Drill on 2 Nov: backup_database 0.9 s, pg_restore into a fresh database 0.7 s; users, allocations, invoices and audit rows identical; verify_audit passes on the restored copy. Nightly schedule gives RPO ≤ 24 h. |
| HMS-NF-004 | Usability and accessibility | TC-UX-01 | **PARTIAL** | 17 | axe-core WCAG 2.1 A/AA audit of 33 pages across 5 roles: 0 violations. Every page checked at 360 px; skip link and keyboard focus present. No 10-user trial held. |
| HMS-NF-005 | Data retention | TC-OPS-02 | **PASS** | — | retention_report lists records older than 5 years; anonymise_old_records --apply blanks the personal data of residents who left over 5 years ago, old visitors and outpass contacts, and keeps the records so they can still be retrieved; dry run by default; scheduled monthly (after fixes D-07, D-08, D-25). |
| HMS-SR-001 | TLS 1.2 or higher | TC-SEC-01 | **PARTIAL** | 6, 17 | HTTPS redirect, HSTS and secure cookies enforced outside development; nginx example allows TLS 1.2+ only. No live TLS scan (no deployed server). |
| HMS-SR-002 | RBAC and session expiry | TC-SEC-02 | **PASS** | — | Every restricted URL refuses every other role with 403; idle session expires at 15 min; a logged-out session cookie is rejected. |
| HMS-SR-003 | Password hashing and MFA | TC-SEC-03 | **PASS** | — | Passwords stored as salted Argon2; Warden and Administrator held at the TOTP step until verified. |
| HMS-SR-004 | Audit logging | TC-SEC-04 | **PASS** | — | Actor, action, time, target and outcome recorded; no edit/delete in the app; database refuses UPDATE/DELETE; hash chain detects tampering. |
| HMS-SR-005 | No cardholder data stored | TC-SEC-05 | **PASS** | — | No card number, CVV or bank credential field exists; card data posted to the gateway page is not stored. |
| HMS-SR-006 | Input validation and injection defence | TC-SEC-06 | **PARTIAL** | 17 | SQL injection and stored-markup tests pass on every page; CSP forbids inline script; queries parameterised. No OWASP ZAP scan run. |

## 4. Exit criteria (Test Plan 5.2)

| Exit criterion | Met? | Notes |
|---|---|---|
| 100% of planned test cases executed | **No, 30 of 31 (97%)** | TC-OPS-AVAIL needs a month of uptime data |
| Every High-priority functional requirement implemented and verified | **Yes** | All 20 functional requirements pass; the differences from the SRS are in `DEVIATIONS.md` |
| No non-functional or security requirement fails | **Yes, with 5 partial** | Nothing fails. NF-001, NF-004, SR-001 and SR-006 are partial, NF-002 is not run |
| All High-severity defects closed | **Yes** | 7 High defects, all fixed and retested |
| RTM shows Pass for every required test case | **No, 26 of 31** | The five others are listed in section 6 |

The team's position: the product meets its functional exit criteria. The non-functional gaps are measurement gaps (they need a production-like server, a month of uptime, ten untrained users or an external scanner), not known failures, and each is recorded in `DEVIATIONS.md` rows 14 and 17.

## 5. Defects

26 defects were found and fixed across the validation. 25 were in the product (D-01 to D-25); the last (D-26) was a date-dependent test.

| Severity | Count | Examples |
|---|---|---|
| High | 7 | D-01 maintenance staff got HTTP 403 on their only page; D-03 SLA escalation emailed nobody; D-04 mess bills raised for residents without a bed |
| Medium | 10 | D-05 a month still running could be billed; D-12 admin Reports in the wrong layout; D-24 damage beyond the deposit showed a ₹0 refund |
| Low | 9 | D-06 ₹0 mess invoices; D-17 no ticket number shown; D-26 weekend-dependent test |
| **Total** | **26** | All closed and retested; none open |

Defect density: 25 product defects in 4,221 measured statements, about 5.9 per thousand statements. The full table with fix and retest for each defect is in `docs/qa/TEST_SUMMARY.md`.

## 6. Open items and accepted risks

| Case | What is missing | Why | Risk |
|---|---|---|---|
| TC-PERF-01 | Load test on a production-like server | Only a laptop is available. Result on the laptop: p95 1.6 s against the 2 s target, 0 failures | Low to medium: a real server is normally faster, but it is not shown |
| TC-OPS-AVAIL | A month of uptime data | A script that checks uptime exists; the project has not run for a month | Low |
| TC-UX-01 | 10-user allocation trial | Needs ten untrained wardens | Low: the audit and 360 px checks pass |
| TC-SEC-01 | Live TLS scan of a deployed server | No deployed server. HTTPS redirect, HSTS and secure cookies are enforced and tested; the nginx example allows TLS 1.2 and above only | Low |
| TC-SEC-06 | OWASP ZAP scan | Not set up in time. Hand-written SQL-injection and stored-markup tests pass on every page; CSP forbids inline script | Low to medium |

## 7. Metrics (Test Plan 14)

| Metric | Value |
|---|---|
| Test case execution | 30 of 31 executed (97%) |
| Pass / partial / not run | 26 / 4 / 1 cases |
| Requirement coverage | 31 of 31 requirements have a test case; 30 have executed evidence |
| Automated tests | 376 run, 376 pass; regression pass rate 100% on the final run |
| Defects | 26 found, 26 fixed, 0 open |
| Performance | p95 1.6 s at 2,000 records (target 2 s), laptop only |
| Security findings | 0 open; no ZAP report |
| Accessibility | 0 axe violations on 33 pages |

## 8. Sign-off

| Role | Name | Signature / date |
|---|---|---|
| QA Lead | Vaishnavi Goyal | |
| Development Lead | Vignesh Nunna | |
| Product Owner | Vishnu S R | |
