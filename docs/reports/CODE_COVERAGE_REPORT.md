# Code Coverage Report

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
| Statements measured | 4223 |
| Statements executed by the 376 tests | 4011 |
| **Statement (line) coverage** | **95.0%** |
| Files measured | 105, of which 56 are fully covered |
| CI quality gate | `coverage report --fail-under=80` (passes) |

Branch coverage is reported separately in [`BRANCH_COVERAGE_REPORT.md`](BRANCH_COVERAGE_REPORT.md). The combined figure that coverage.py prints (lines and branches together) is 93.2%.

## 2. Method

- Tool: coverage.py 7.17 in branch mode, started with `coverage run manage.py test`.
- Measured source: everything under `apps/` and `hms/`.
- Not measured, on purpose: migrations, the test files themselves, `manage.py`, the WSGI/ASGI stubs, and the two load-test data generators (`seed_performance_data.py`, `seed_perf_wardens.py`), which only build data for the Locust run in `docs/performance/` and are not product code. Counting them would lower the statement figure to 92.3% (122 more statements, none run).
- Settings are in `pyproject.toml` (`[tool.coverage.*]`); CI runs the same command and fails the build under 80%.

## 3. Coverage by module

| Module | Responsibility | Statements | Not executed | Line coverage |
|---|---|---|---|---|
| `apps/accounts` | Accounts, RBAC, sessions, MFA | 427 | 11 | **97.4%** |
| `apps/admissions` | Admission, allocation, transfer, vacating | 1008 | 36 | **96.4%** |
| `apps/audit` | Audit log, backup, security hooks | 277 | 23 | **91.7%** |
| `apps/complaints` | Complaints and SLA escalation | 245 | 12 | **95.1%** |
| `apps/fees` | Invoices, payment, receipts, overdue | 560 | 14 | **97.5%** |
| `apps/gate` | Gate, outpass, curfew, attendance | 605 | 41 | **93.2%** |
| `apps/mess` | Mess menu, opt-out, billing | 372 | 47 | **87.4%** |
| `apps/reporting` | Reports and exports | 185 | 0 | **100.0%** |
| `apps/visitors` | Visitors | 170 | 9 | **94.7%** |
| `hms` | Project shell: settings, dashboard, API, admin site | 374 | 19 | **94.9%** |
| **Total** | | **4223** | **212** | **95.0%** |

## 4. Files that are not fully covered

49 of 105 files have at least one statement the tests do not reach. Lowest coverage first:

| File | Statements | Not executed | Coverage | Lines not executed |
|---|---|---|---|---|
| `apps/audit/management/commands/backup_database.py` | 56 | 17 | 70% | 41, 87, 88, 90, 91, 92, 93, 94, 96, 97, 99, 106, 107, 112, 113, 120, 123 |
| `apps/mess/views.py` | 191 | 36 | 81% | 60, 81, 82, 83, 84, 117, 118, 119, 120, 144, 151, 152, 178, 179, 180, 181, 191, 192, 199, 227, 228, 229, 230, 249, 250, 251, 252, 324, 325, 332, 333, 334, 341, 342, 356, 366 |
| `apps/mess/dashboard.py` | 29 | 5 | 83% | 30, 33, 58, 59, 60 |
| `apps/gate/views.py` | 98 | 15 | 85% | 34, 35, 57, 105, 106, 137, 138, 180, 181, 182, 183, 209, 210, 211, 212 |
| `apps/accounts/management/commands/totp_code.py` | 16 | 2 | 88% | 18, 21 |
| `apps/audit/management/commands/retention_report.py` | 24 | 3 | 88% | 38, 43, 44 |
| `apps/mess/admin.py` | 24 | 3 | 88% | 33, 34, 35 |
| `apps/accounts/permissions.py` | 49 | 6 | 88% | 58, 59, 60, 61, 62, 63 |
| `hms/admin_site.py` | 49 | 6 | 88% | 55, 99, 100, 101, 102, 103 |
| `apps/gate/services.py` | 166 | 20 | 88% | 44, 56, 76, 133, 137, 219, 220, 224, 240, 244, 269, 279, 282, 287, 313, 333, 372, 382, 445, 465 |
| `hms/api.py` | 43 | 5 | 88% | 46, 52, 54, 56, 59 |
| `apps/complaints/management/commands/escalate_complaints.py` | 36 | 4 | 89% | 23, 68, 69, 73 |
| `hms/templatetags/hms_extras.py` | 10 | 1 | 90% | 13 |
| `apps/visitors/views.py` | 82 | 8 | 90% | 65, 66, 69, 70, 94, 95, 120, 121 |
| `apps/admissions/erp.py` | 11 | 1 | 91% | 22 |
| `apps/complaints/dashboard.py` | 22 | 2 | 91% | 33, 34 |
| `apps/fees/dashboard.py` | 23 | 2 | 91% | 26, 28 |
| `apps/complaints/admin.py` | 13 | 1 | 92% | 49 |
| `apps/admissions/vacating.py` | 131 | 10 | 92% | 40, 83, 165, 168, 234, 239, 295, 300, 301, 306 |
| `apps/admissions/admin.py` | 94 | 7 | 93% | 118, 119, 120, 121, 137, 139, 140 |
| `apps/audit/management/commands/anonymise_old_records.py` | 42 | 3 | 93% | 27, 28, 40 |
| `apps/complaints/forms.py` | 17 | 1 | 94% | 41 |
| `apps/mess/forms.py` | 18 | 1 | 94% | 32 |
| `apps/admissions/services.py` | 41 | 2 | 95% | 54, 55 |
| `hms/dashboard.py` | 23 | 1 | 96% | 31 |
| `apps/mess/models.py` | 47 | 2 | 96% | 40, 114 |
| `apps/admissions/views.py` | 217 | 9 | 96% | 55, 56, 149, 208, 214, 342, 343, 517, 543 |
| `apps/fees/views.py` | 73 | 3 | 96% | 62, 63, 86 |
| `apps/admissions/dashboard.py` | 25 | 1 | 96% | 57 |
| `hms/forms.py` | 26 | 1 | 96% | 13 |
| `hms/navigation.py` | 52 | 2 | 96% | 382, 401 |
| `apps/gate/models.py` | 79 | 3 | 96% | 71, 101, 199 |
| `apps/fees/services.py` | 137 | 5 | 96% | 333, 343, 346, 350, 420 |
| `hms/security.py` | 29 | 1 | 97% | 42 |
| `apps/complaints/views.py` | 90 | 3 | 97% | 89, 90, 148 |
| `apps/gate/dashboard.py` | 30 | 1 | 97% | 29 |
| `apps/visitors/models.py` | 33 | 1 | 97% | 67 |
| `apps/admissions/forms.py` | 37 | 1 | 97% | 95 |
| `apps/accounts/models.py` | 41 | 1 | 98% | 64 |
| `hms/views.py` | 42 | 1 | 98% | 97 |
| `apps/fees/api.py` | 45 | 1 | 98% | 65 |
| `apps/admissions/models.py` | 244 | 5 | 98% | 138, 155, 361, 489, 517 |
| `apps/accounts/views.py` | 52 | 1 | 98% | 46 |
| `apps/fees/models.py` | 108 | 2 | 98% | 168, 172 |
| `apps/complaints/models.py` | 56 | 1 | 98% | 98 |
| `apps/gate/api.py` | 116 | 2 | 98% | 192, 193 |
| `apps/fees/admin.py` | 64 | 1 | 98% | 92 |
| `hms/settings.py` | 68 | 1 | 99% | 181 |
| `apps/accounts/management/commands/seed_demo.py` | 91 | 1 | 99% | 95 |

## 5. What the uncovered lines are

Each group below is traced to the functions that hold the unexecuted lines:

- **`backup_database.py` (`handle`):** the paths that run `pg_dump`, which needs the PostgreSQL client tools that the CI image does not install. Backup and restore were verified by the timed drill on 2 November (TC-OPS-01), not by a unit test.
- **Notification failures:** `_notify_guardian` and `_notify_wardens` in `apps/gate/services.py`, `_send_overdue_reminder` in `apps/fees/services.py`: the branches that handle a mail failure. The retry of a failed curfew or overdue send is tested; these are the secondary paths.
- **View refusals and redirects:** `apps/mess/views.py` (`_resident_choice`, `_prefilled_form`, `meal_delete`, `record_served`, `_generate_bills`), `apps/complaints/views.py` (`update_complaint_status`), `apps/visitors/views.py` (`visitor_entry`, `visitor_exit`): alternate redirects and form-error messages. The success path of each is covered by the acceptance tests.
- **`RoleRequiredMixin.dispatch` in `apps/accounts/permissions.py`:** no view uses this class-based helper (every view uses the `role_required` decorator, which is fully covered), so these six lines are unused code, not an untested feature.
- **API error envelope:** `exception_handler` in `hms/api.py`, the branches for rare database errors.
- **Django admin overrides:** `delete_model` and `changelist_view` in `apps/admissions/admin.py` and `module_view` in `hms/admin_site.py`, used only from the admin screens.

The unexecuted lines are error and alternate-redirect paths. The success path of every Test Plan case is exercised (see the System Validation Report).

## 6. Evidence

- [`coverage-html/index.html`](coverage-html/index.html): browsable report, every file with the executed and missed lines highlighted (open in a browser).
- [`coverage-summary.txt`](coverage-summary.txt): the same table as text, with missing line numbers.
- [`coverage.xml`](coverage.xml): Cobertura XML for tools.

## 7. How to repeat

```bash
pip install -r requirements-dev.txt
coverage run manage.py test
coverage report              # text
coverage html -d htmlcov     # browsable
```
