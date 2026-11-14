# Unit Test Report

| Item | Detail |
|---|---|
| **Project** | Hostel Management System (HMS), Team 1 |
| **Build tested** | Release `v1.0` (`main` at 0f9d3d8); numbers re-verified on 12 November 2026 |
| **Date** | 8 November 2026; re-run and verified 12 November 2026 (same results) |
| **Environment** | Fedora 42, Python 3.13.13 (CI uses 3.12), Django 5.2.18, PostgreSQL 16, `DJANGO_DEBUG=false` (the CI configuration) |
| **Prepared by** | Vignesh Nunna (PES2UG24CS582) |
| **QA lead review** | Vaishnavi Goyal (PES2UG24CS571) |

## 1. Result

| Measure | Value |
|---|---|
| Tests run | **376** |
| Passed | **376** |
| Failed / errors / skipped | 0 / 0 / 0 |
| Run time | about 1 minute (78 s on 8 November, 60 s on 12 November) |
| Lint (`ruff check .`) | no findings |
| Django checks, migrations check, deployment check | all clean |

The first run on 8 November, on the unchanged `main`, had **one failure** (defect D-26, section 4). It was a flaw in the test, not in the product, and the run above is after the fix.

## 2. How the tests are organised

The Test Plan (section 5.2) names four levels. Every test lives next to the module it checks and runs with one command:

- **Unit:** services, models, validators and serializers called directly (for example `apps/admissions/test_vacating.py`, `apps/mess/test_services.py`).
- **Integration:** REST endpoints and pages with the database, the mock payment gateway and the mail backend (for example `apps/fees/tests.py`, `apps/gate/test_api_extra.py`).
- **System / acceptance:** `hms/test_acceptance.py` has one or more tests for each Sprint 2 Test Plan case, driven through the pages each role uses; `hms/test_screens.py` walks every role's screens.
- **Security:** `hms/test_security.py` and `apps/accounts/test_rbac.py`.

## 3. Results by test file

| File | Level | Tests | What it checks | Requirements |
|---|---|---|---|---|
| `apps/accounts/test_auth.py` | Unit / integration | 20 | Argon2 storage, 15-minute sessions, MFA step, API sign-in | HMS-SR-002, SR-003 |
| `apps/accounts/test_rbac.py` | Unit / integration | 2 | Access matrix: every restricted URL against every other role | HMS-SR-002 |
| `apps/accounts/tests.py` | Unit / integration | 28 | Users, roles, sign-in pages, profile, password change | HMS-SR-002, SR-003 |
| `apps/admissions/test_allocation.py` | Unit / integration | 41 | Ranking, automatic and manual allocation, room inventory rules | HMS-F-002, F-061 |
| `apps/admissions/test_transfer.py` | Unit / integration | 17 | Transfer between beds in one transaction | HMS-F-003 |
| `apps/admissions/test_vacating.py` | Unit / integration | 10 | No-dues clearances, refund arithmetic, bed release (services) | HMS-F-062 |
| `apps/admissions/test_vacating_views.py` | Unit / integration | 11 | The same workflow through the resident and warden pages | HMS-F-062 |
| `apps/admissions/tests.py` | Unit / integration | 31 | Admission form, validation, duplicates, applications API | HMS-F-001 |
| `apps/audit/test_backup_database.py` | Unit / integration | 3 | Backup command and file handling | HMS-NF-003 |
| `apps/audit/tests.py` | Unit / integration | 24 | What is logged, append-only table, hash chain, tamper detection | HMS-SR-004 |
| `apps/complaints/tests.py` | Unit / integration | 3 | SLA deadlines and escalation | HMS-F-042 |
| `apps/fees/tests.py` | Unit / integration | 54 | Invoices, mock gateway callbacks, receipts, overdue reminders, no card data | HMS-F-010 to F-013, SR-005 |
| `apps/gate/test_api_extra.py` | Unit / integration | 21 | Gate REST API error paths and roles, outpass and attendance endpoints, scheduled commands | HMS-F-020 to F-023 |
| `apps/gate/tests.py` | Unit / integration | 30 | Gate movements, curfew alerts, outpass, night attendance | HMS-F-020 to F-023 |
| `apps/mess/test_services.py` | Unit / integration | 7 | Publishing, week grid, headcount, month figures | HMS-F-030, F-031 |
| `apps/reporting/tests.py` | Unit / integration | 15 | Report figures and PDF/XLSX exports | HMS-F-060 |
| `apps/visitors/tests.py` | Unit / integration | 9 | Visiting hours, override with reason, exit time | HMS-F-050 |
| `hms/test_acceptance.py` | System / acceptance | 17 | One acceptance test per Sprint 2 Test Plan case, through the pages each role uses | TS-1 to TS-8 |
| `hms/test_screens.py` | System (UI) | 13 | Every role's screens, navigation, no placeholder pages | HMS-NF-004 |
| `hms/test_security.py` | Security | 20 | TLS settings, input handling (SQL injection, stored markup), CSP, parameterised queries | HMS-SR-001, SR-006 |
| **Total** | | **376** | | |

Every test passed. The per-test list with names is in [`unit-test-run.txt`](unit-test-run.txt).

## 4. Defect found during this run

| ID | Severity | Defect | Fix | Retest |
|---|---|---|---|---|
| D-26 | Low (test only) | `test_tc_mess_01_manager_plans_the_week` published a meal for "two days from now" and then copied "this week". On a Saturday or Sunday that meal falls in *next* week, so nothing was copied and the test failed. It would have failed in CI on every weekend, including on a viva day. | The test works out the meal's own week before copying. | Passes; full suite 376/376 |

## 5. Tests added in this cycle

The suite grew from 337 to 376 tests to close the gaps the coverage run showed (see the Code Coverage Report):

| File | New tests | Why |
|---|---|---|
| `apps/gate/test_api_extra.py` | 21 | The gate REST API was only 59% covered: error paths (unknown resident, bad body, no bed), role checks, the outpass and attendance endpoints, the device-key "not configured" case, and the two scheduled commands (`process_curfew_alerts`, `process_overdue_invoices`) that had no test at all |
| `apps/mess/test_services.py` | 7 | Publishing rights, headcount, week grid, week clamping and the month-so-far bill |
| `apps/admissions/test_vacating_views.py` | 11 | The vacating pages (HMS-F-062) had their rules tested but not the pages a warden and resident use: refusals, role checks, the full workflow to bed release |

## 6. How to repeat

```bash
export POSTGRES_DB=hms DJANGO_SECRET_KEY=any DJANGO_DEBUG=false
python manage.py test                 # all 376 tests
python manage.py test apps.fees       # one module
python manage.py test --verbosity 2   # list every test
```

The same command runs on every pull request in GitHub Actions (`.github/workflows/ci.yml`).
