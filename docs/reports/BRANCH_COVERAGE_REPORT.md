# Branch Coverage Report

| Item | Detail |
|---|---|
| **Project** | Hostel Management System (HMS), Team 1 |
| **Build tested** | `main` at 9f65069 plus the changes in this pull request |
| **Date** | 8 November 2026 |
| **Environment** | Fedora 42, Python 3.13.13 (CI uses 3.12), Django 5.2.18, PostgreSQL 16, `DJANGO_DEBUG=false` (the CI configuration) |
| **Prepared by** | Vignesh Nunna (PES2UG24CS582) |
| **QA lead review** | Vaishnavi Goyal (PES2UG24CS571) |

## 1. Result

| Measure | Value |
|---|---|
| Branches measured (each side of an `if`, loop or `try`) | 734 |
| Branches taken by the 376 tests | 608 |
| Branches never taken | 126 |
| Lines where only one side was taken (partial) | 106 |
| **Branch coverage** | **82.8%** |
| Files with branches / fully covered | 61 / 17 |

Branch coverage is always lower than line coverage (95.0%) because a line can run while only one outcome of its decision is ever tried. That is the case for most of the 126 untaken branches here: the "everything is fine" side is tested, the rarer side (a refusal, a database error) is not always.

## 2. Method

Same run as the Code Coverage Report: coverage.py with `branch = true` (`pyproject.toml`), over `apps/` and `hms/`, with the same exclusions. coverage.py counts a branch as every possible jump from a decision, so a plain `if` with no `else` has two.

## 3. Branch coverage by module

| Module | Branches | Taken | Never taken | Partial lines | Branch coverage |
|---|---|---|---|---|---|
| `apps/accounts` | 94 | 84 | 10 | 6 | **89.4%** |
| `apps/admissions` | 164 | 144 | 20 | 20 | **87.8%** |
| `apps/audit` | 52 | 36 | 16 | 6 | **69.2%** |
| `apps/complaints` | 42 | 31 | 11 | 11 | **73.8%** |
| `apps/fees` | 66 | 56 | 10 | 10 | **84.8%** |
| `apps/gate` | 114 | 99 | 15 | 15 | **86.8%** |
| `apps/mess` | 72 | 50 | 22 | 18 | **69.4%** |
| `apps/reporting` | 22 | 22 | 0 | 0 | **100.0%** |
| `apps/visitors` | 22 | 17 | 5 | 5 | **77.3%** |
| `hms` | 86 | 69 | 17 | 15 | **80.2%** |
| **Total** | **734** | **608** | **126** | **106** | **82.8%** |

Reporting is fully covered. Accounts, admissions and gate are above 85%. The lowest are audit (the backup command needs `pg_dump`), mess, complaints and visitors, whose views have many small refusal and redirect branches.

## 4. Files with the most untaken branches

| File | Branches | Never taken | Branch coverage |
|---|---|---|---|
| `apps/mess/views.py` | 50 | 16 | 68.0% |
| `apps/audit/management/commands/backup_database.py` | 22 | 13 | 40.9% |
| `apps/gate/services.py` | 68 | 12 | 82.4% |
| `apps/admissions/vacating.py` | 40 | 9 | 77.5% |
| `apps/admissions/views.py` | 46 | 7 | 84.8% |
| `apps/complaints/views.py` | 26 | 7 | 73.1% |
| `apps/visitors/views.py` | 20 | 5 | 75.0% |
| `apps/accounts/permissions.py` | 16 | 4 | 75.0% |
| `apps/fees/services.py` | 30 | 4 | 86.7% |
| `hms/api.py` | 14 | 4 | 71.4% |
| `hms/admin_site.py` | 6 | 3 | 50.0% |
| `apps/accounts/management/commands/totp_code.py` | 4 | 2 | 50.0% |

## 5. Reading the gaps

| Where | Untaken side | Risk | Next step |
|---|---|---|---|
| `backup_database.py` | `pg_dump` / `pg_restore` options and failure paths | Low: the happy path was timed in the restore drill (TC-OPS-01) | Install the PostgreSQL client in the CI image and add a restore test |
| `apps/mess/views.py` | Form errors and refusals in `meal_save`, `meal_delete`, `record_served`, `_generate_bills`; the resident-choice helper | Low: the rules behind them (24-hour notice, ended months only, no double billing) are tested in the acceptance suite | Add one form-error test per view |
| `apps/gate/services.py` | Guardian and warden notification failures; late-return edge cases | Low: the retry of a failed curfew alert is tested | Test the guardian-email failure path |
| `apps/admissions/vacating.py` | State errors in `complete_vacating`, `approve_vacating_request` | Low: the main refusals (dues unpaid, clearances pending, not approved, damage after approval) are tested | Add the remaining state-error tests |
| `apps/complaints/views.py`, `apps/visitors/views.py` | Refusals by status or by the wrong actor | Low: access by role is covered by the access-matrix test | Add one test per refusal |
| `apps/accounts/permissions.py` | `RoleRequiredMixin` is unused | None | Remove the unused class or use it |

The untaken branches are second-order cases: the "everything is fine" side and the main refusal of each Test Plan case are both tested.

## 6. Evidence

- [`coverage-html/index.html`](coverage-html/index.html): in the browsable report each partially covered line is highlighted and shows the jump that was never taken (for example `line 93 didn't jump to line 94`).
- [`coverage-summary.txt`](coverage-summary.txt): text version; the `BrPart` column is the partial lines.
- [`coverage.xml`](coverage.xml): per-line `branch="true"` entries with `condition-coverage`.

## 7. How to repeat

```bash
coverage run manage.py test
coverage report -m     # BrPart and Missing columns
coverage html          # open htmlcov/index.html
```
