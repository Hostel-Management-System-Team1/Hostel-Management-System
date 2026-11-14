# Hostel Management System

Team 1 Software Engineering Project.

| SRN | Name | GitHub |
|---|---|---|
| PES2UG24CS571 | Vaishnavi Goyal | whyshoee |
| PES2UG24CS582 | Vignesh Nunna | Greninja34 |
| PES2UG24CS595 | Vishnu S R | vishnusr594-afk |
| PES2UG24CS615 | Yellala Sai Aneesh Reddy | saianeesh-debug |

Design documents: [SRS](docs/srs/PES2UG24CS571_582_595_615_Team1_SRS.pdf) ·
[SAD](docs/sad/PES2UG24CS571_582_595_615_Team1_SAD.pdf) ·
[Test Plan](docs/test-plan/PES2UG24CS571_582_595_615_Team1_Software_Test_Plan_Final.pdf) ·
[Deviations](DEVIATIONS.md)

## Tech stack (SAD 3.6)

- Python 3.12, Django 5.2, Django REST Framework
- Django templates with Bootstrap 5
- PostgreSQL 16

## Who signs in where

Everyone signs in at http://127.0.0.1:8000. What they see depends on their role (SRS 2.3):

| Role | Lands on | What they get |
|---|---|---|
| Resident, Warden, Security Guard, Maintenance Staff, Mess Manager | **Portal** (`/`) | A sidebar and dashboard with only their own screens |
| Hostel Administrator | **Admin site** (`/admin/`) | An HMS dashboard (live account counts, recent activity), user and role management, and the administrator screens |

The role decides access: setting a user's role to *Hostel Administrator* gives them full rights in
the admin site, and any other role limits them to the portal. Each role's sidebar is listed in
[`hms/navigation.py`](hms/navigation.py); the admin dashboard's module cards come from the same list.
Each module adds its own panels to the role dashboards from its `dashboard.py`.

| Role | Sidebar |
|---|---|
| Resident | Room application, Fees & receipts, Vacating, Outpass, Meals, My complaints |
| Warden | Applications, Rooms, Residents, Vacating requests, Outpasses, Night attendance, Complaints, Gate log, Visitors, Reports |
| Security Guard | Gate log, Visitors, Resident returns |
| Maintenance Staff | Complaints assigned to them |
| Mess Manager | Menu & bills |
| Hostel Administrator | Applications, Residents, Fees, Complaints, Mess, Gate log, Outpasses, Visitors, masters (blocks, rooms, fee structure, allocation order, curfew times, visiting hours), Users & roles, Reports, Audit log |

To add people, sign in as an administrator and use **Users & roles → Add user**.

### Sign-in security (HMS-SR-002, HMS-SR-003)

- **Passwords** are stored only as salted Argon2 hashes.
- **Sessions** end after 15 minutes without a request, and signing out deletes the session on the
  server, so a copied session cookie stops working.
- **Warden and Administrator** accounts need a second step: after the password, a 6-digit code from an
  authenticator app (TOTP). The first sign-in shows a QR code to link the app; after that only the code
  is asked. An administrator can reset a lost device by deleting it under *TOTP devices* in the admin site.
- **Access control**: every restricted screen and API endpoint lists the roles allowed to use it
  (`apps/accounts/permissions.py`); anyone else gets HTTP 403. `apps/accounts/test_rbac.py` walks the URL
  configuration and tries every role against every restricted URL.
- For demos and local testing, `python manage.py totp_code <username>` prints the current code for an
  account that has linked an app. It refuses to run unless `DJANGO_DEBUG` is on.
- API errors use one envelope, `{timestamp, path, status, error, message, traceId}` (SAD 4.4).

## Admission (HMS-F-001)

A resident fills in one application per session (personal, academic, guardian, medical and room-preference
details) and gets an application number such as `HMS-2026-00001`. A second application for the same enrolment
number in the same session is refused with a message naming the first. The warden approves or rejects each
application (a rejection needs a reason). Medical and guardian details are visible only to the applicant and the
warden; the administrator's view of an application leaves out the medical details.

The same rules back the REST endpoint `POST /api/v1/applications` (SAD 4.3): 201 with
`{applicationNumber, status}`, 400 for invalid data, 409 for a duplicate.

## Room inventory and allocation (HMS-F-002, HMS-F-061)

The administrator keeps the inventory in the admin site under **Masters**: blocks (each for one gender),
rooms (floor, type, bed capacity, status) and the **allocation order** (merit, seniority or first come). A
room's beds are created from its capacity. A room with an occupied bed cannot be deleted.

The warden opens an approved application and allocates the suggested bed (or picks another vacant one), or uses
**Allocate all in ranked order**. Only vacant, in-service beds in a block for the applicant's gender are
offered, matching the requested room type and preferred block; the gender rule is also enforced when an
allocation is saved. `POST /api/v1/allocations` does the same for one application (201, 404, or 409 when no
bed matches).

## Room transfer (HMS-F-003)

The warden opens **Residents**, picks a resident and chooses a vacant bed (only beds in a block for the resident's
gender are listed) with a required reason. The old bed becomes vacant, the new one occupied and the move is
recorded with the reason, the warden and the time, all in one database transaction. The resident's history of
moves is shown on the same page.

## Fees, payment and receipts (HMS-F-010 – F-012)

When a bed is allocated the system raises an itemised invoice from the **fee structure** (administrator:
Masters → Fee structure; a starting structure is installed). The resident opens **Fees & receipts**, chooses a
payment method and is sent to the payment gateway's page. A successful signed callback marks the invoice Paid and
issues a receipt with a unique number (`RCT-2026-000001`), downloadable as a PDF; a failed or cancelled payment
leaves the invoice Unpaid.

The gateway here is a bundled stand-in that asks for no card details (see DEVIATIONS.md). The callback endpoint
`POST /api/v1/payments/callback` accepts only requests signed with `HMS_PAYMENT_SECRET`; set a real secret outside
development. `POST /api/v1/invoices/{id}/payments` starts a payment (201, 404, 409, or 502 when the gateway is down).

`python manage.py expire_payments` marks payment sessions nobody finished as Abandoned.

### Overdue fees (HMS-F-013)

`python manage.py process_overdue_invoices` (run daily, just after midnight) marks every unpaid invoice whose due
date has passed as Overdue and emails one reminder to the resident, with the guardian in BCC. The reminder time is
stored only after the email is sent, so a failed send is retried on the next run and nobody is reminded twice.

## Gate, outpass and night attendance (HMS-F-020 – F-023)

- **Gate log.** Readers post entries and exits to `POST /api/v1/gate/movements/device` with the
  `X-Gate-Device-Key` header (set `GATE_DEVICE_API_KEY`); the event's own time is kept and a repeated event id is
  ignored. When a reader is not used, the guard opens **Gate log**, finds the resident by name or room and presses
  *Record exit* or *Record entry* (also `POST /api/v1/gate/movements/manual`). The warden sees the same log.
- **Curfew.** Each block has a curfew time (admin: *Masters → Curfew times*). `python manage.py
  process_curfew_alerts`, run every few minutes, raises an alert for a resident still out 30 minutes after
  curfew and emails the wardens; alerts show on the warden's dashboard and gate log.
- **Outpass.** A resident with a bed asks for leave (destination, contact number, return time). The warden
  approves or rejects it under **Outpasses**; the guardian is emailed on approval and again when the guard records
  the return under **Resident returns**.
- **Night attendance.** The warden generates the register for a night under **Night attendance**: each resident is
  Present (gate log), On leave (approved outpass) or Absent, room by room.

## Mess menu, opt-outs and bills (HMS-F-030, F-031)

The mess manager publishes each meal (date, time, menu) under **Menu & bills**; residents see the week under
**Meals** and can skip a meal until 24 hours before it is served. **Generate bills** raises one mess invoice per
resident for a month: ₹50 for every published meal they did not skip. Running it again for the same month does not
bill twice. Mess invoices appear beside hostel fees under **Fees & receipts**.

## Complaints (HMS-F-040 – F-042)

A resident reports a problem (title, category, description, optional photo up to 5 MB) under **My complaints**. The
category sets the priority: Maintenance is High (48-hour SLA), Cleaning Medium (96 hours), Noise and Other Low. The
warden assigns each complaint to maintenance staff, who see only their own under **Complaints** and mark them
resolved; the resident then confirms the fix, which closes it. `python manage.py escalate_complaints`, run hourly,
emails every Hostel Administrator about complaints past their SLA and records the escalation in the audit log.

## Visitors (HMS-F-050)

The guard registers a visitor (name, phone, identity document, resident visited, purpose) and records entry and
exit under **Visitors**. Outside visiting hours (admin: *Masters → Visiting hours*; with none set, every entry
counts as out of hours) entry is refused until the warden opens the visitor and allows it with a reason; the
override is written to the audit log.

## Reports (HMS-F-060)

Wardens open **Reports** in the portal and administrators in the admin site: bed occupancy, outstanding dues,
complaint ageing and mess activity, each downloadable as CSV, Excel (XLSX) or PDF.

## Vacating and deposit refund (HMS-F-062)

A resident asks to vacate under **Vacating**. Three no-dues clearances (hostel fees, mess dues, maintenance) are
created; hostel and mess cannot be cleared while their invoices are unpaid. The warden records the clearances and any
damage charges, approves the request, then completes it: the bed returns to the vacant pool and the refund is the
paid security deposit minus outstanding dues and damage charges. When the damage is more than the deposit, the
difference is shown as payable and raised as an invoice to the resident.

## Audit log and security protections (HMS-SR-001, SR-004 – SR-006)

- **Audit log** (administrator: *Audit log* in the admin site). Every allocation and transfer, invoice and
  payment, application decision, account change (created, role or status changed, password changed, deleted),
  sign-in, sign-out, failed sign-in, second-step result and refused request writes an entry
  with actor, action, time, target and outcome. Entries are append-only: the application offers no way to edit
  or delete them and the database refuses `UPDATE` and `DELETE` on the table. Each entry also stores a hash chained
  to the one before it, so a change made behind the application's back is detected: the page shows an integrity
  banner, and `python manage.py verify_audit` (suitable for cron) fails if anything was changed or removed. Keep the
  head hash it prints somewhere else too; it also exposes entries cut off the end of the log. The log never holds
  medical, guardian or identity details, passwords or card data.
- **TLS.** Outside development (`DJANGO_DEBUG=false`) Django redirects HTTP to HTTPS, sends HSTS and marks cookies
  secure. The TLS 1.2 minimum is set on the web server: see `deploy/nginx.conf.example`; set `HMS_BEHIND_PROXY=true`
  behind it. CI runs `manage.py check --deploy`.
- **Payments.** No card number, CVV or bank credential is stored: the payment models have no such fields, and a test
  checks it.
- **Input.** Forms validate every field and refuse markup in free text; templates escape output; a
  Content-Security-Policy forbids inline script; all queries go through the ORM (a test fails if raw SQL is added);
  input the database cannot store is a 400, not a crash. Failed sign-ins are written to the audit log; limiting
  how fast requests arrive is left to the web server (`limit_req` in `deploy/nginx.conf.example`).

## Operations (HMS-NF-001 – NF-005)

- **Backup.** `python manage.py backup_database` writes a timestamped `pg_dump` to `HMS_BACKUP_DIR` (default
  `../hms-backups`). Schedule it nightly with cron, or on Windows with `deploy/windows/backup_nightly.bat`, which also
  keeps the last 7 days.
- **Uptime.** `deploy/windows/check_uptime.ps1` requests the home page and appends the result to
  `monitoring/uptime.csv`; schedule it every few minutes.
- **Retention.** `python manage.py retention_report --years 5` counts admission, fee, gate, outpass and visitor records
  older than the retention period. `python manage.py anonymise_old_records --years 5 --apply` then blanks the personal
  details of residents who left more than 5 years ago (name, contacts, guardian, medical, enrolment number), of old
  visitor records and of old outpass contacts. The records themselves stay, so history can still be retrieved;
  without `--apply` it only reports.
- **Performance.** [`performance/locustfile.py`](performance/locustfile.py) drives 200 users against 2,000 seeded residents
  (`seed_performance_data`, `seed_perf_wardens`). The measured results are in
  [`docs/performance/`](docs/performance/performance_test_summary.txt).
- **QA.** The Test Plan results, defects and open items are in [`docs/qa/TEST_SUMMARY.md`](docs/qa/TEST_SUMMARY.md),
  with per-case evidence in `docs/qa/HMS_QA_Test_Execution_Register.xlsx`. `hms/test_acceptance.py` holds one
  acceptance test per Sprint 2 Test Plan case.

### Scheduled jobs

| Command | When |
|---|---|
| `process_overdue_invoices` | daily, 00:05 |
| `process_curfew_alerts` | every 5 minutes in the evening |
| `escalate_complaints` | hourly |
| `expire_payments` | every 30 minutes |
| `backup_database` | nightly |
| `verify_audit` | daily |
| `anonymise_old_records --apply` | monthly |

## UI design

The portal and admin use one light theme on Bootstrap 5: `static/css/hostel.css` (portal) and
`static/css/admin.css` (admin site), with shared colour tokens at the top of each file.

## Project layout

A modular monolith (SAD 3.5): one Django project, one Django app per service module (SAD 3.4).

| App | SAD service module | Requirements |
|---|---|---|
| `apps/accounts` | Auth & RBAC Service | HMS-SR-002, HMS-SR-003 |
| `apps/admissions` | Admission & Allocation Service | HMS-F-001 – F-003 |
| `apps/fees` | Fee & Payment Service | HMS-F-010 – F-013 |
| `apps/gate` | Gate & Outpass Service | HMS-F-020 – F-023 |
| `apps/mess` | Mess Service | HMS-F-030, F-031 |
| `apps/complaints` | Complaint Service | HMS-F-040 – F-042 |
| `apps/visitors` | Visitor Service | HMS-F-050 |
| `apps/reporting` | Reporting & Admin Service | HMS-F-060 – F-062 |
| `apps/audit` | Audit Service | HMS-SR-004, HMS-NF-003, HMS-NF-005 |

## Running locally

### 1. PostgreSQL (one-time setup, Fedora)

```bash
sudo dnf install -y postgresql-server postgresql
sudo postgresql-setup --initdb
# allow password logins over localhost (Fedora defaults to "ident")
sudo sed -i -E 's/^(host.*all.*all.*)ident$/\1scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
sudo systemctl enable --now postgresql

# database user and database used by the app (see .env.example)
sudo -u postgres psql -c "CREATE USER hms WITH PASSWORD 'hms' CREATEDB;"
sudo -u postgres createdb -O hms hms
```

`CREATEDB` lets Django create its temporary test database when you run the tests.

### 2. The app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python manage.py migrate
python manage.py createsuperuser   # creates a Hostel Administrator
python manage.py runserver
```

Open http://127.0.0.1:8000 for the portal and http://127.0.0.1:8000/admin for the admin site.

### Demo data

```bash
python manage.py seed_demo
```

creates one account per role (`admin`, `warden`, `guard`, `maintenance`, `mess`, and residents `aarav`, `diya`,
`rohan`, `isha`, `neha`, `omar`, all with password `demo-pass-123`) and sample data for every module: four residents
with a bed and an invoice, a week's menu with opt-outs, gate movements and a curfew alert, a pending and an approved
outpass, complaints in each state, visitors and a vacating request. `neha` and `omar` have not applied yet, for
trying the application form. It is safe to re-run and refuses to run unless `DJANGO_DEBUG` is on. `admin` and `warden` have an authenticator app already linked; read their
second-step code with `python manage.py totp_code warden`.

The app connects to the `hms` database as user `hms` on localhost. To use different
settings, set the `POSTGRES_*` environment variables listed in `.env.example`.

## Running checks and tests

```bash
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

```bash
coverage run manage.py test
coverage report -m          # add `coverage html` for a browsable report
```

### CI/CD pipeline (GitHub Actions)

One workflow, [`ci-cd.yml`](.github/workflows/ci-cd.yml), with three stages:

| Stage | Runs on | What it does |
|---|---|---|
| **Build and unit tests** | every pull request, push to `main`, `v*` tag | lint (`ruff check` as annotations on the changed lines, `ruff format --check`), Django checks, migrations check, deployment security check, then all 376 unit and integration tests under coverage.py with branch coverage, against PostgreSQL 16 |
| **Coverage & Quality Gate** | after the stage above | fails unless every test passed and total coverage is at least 80% ([`quality_gate.py`](.github/scripts/quality_gate.py)) |
| **Deploy to Staging/Production** | push to `main` or a `v*` tag only (skipped on pull requests) | builds the [`Dockerfile`](Dockerfile) image and pushes it to the GitHub Container Registry, starts that exact image with a fresh PostgreSQL, migrates, runs the [smoke test](.github/scripts/smoke_test.sh); on a tag it also creates a GitHub Release with the reports and the SRS, SAD and Test Plan attached |

Every run shows a **job summary**: tests passed and failed per module, every unit test with its
result, statement and branch coverage per module, the slowest tests and the failure messages. A
failed test is also an **annotation** on the file and line where it failed
([`ci_report.py`](.github/scripts/ci_report.py) reads the JUnit XML that
[`junit_runner.py`](.github/scripts/junit_runner.py) writes). The reports are uploaded as the
`test-reports` artifact for 30 days.

There is no production server for this project, so the deploy stage runs the image on the runner;
rolling out to a real host is one more step there, using the same image. The image runs only the
application under gunicorn; TLS and static files stay with the reverse proxy
([`deploy/nginx.conf.example`](deploy/nginx.conf.example)).

### Test reports (`docs/reports/`)

| Report | File |
|---|---|
| Unit test report | [`UNIT_TEST_REPORT.md`](docs/reports/UNIT_TEST_REPORT.md) |
| System validation report | [`SYSTEM_VALIDATION_REPORT.md`](docs/reports/SYSTEM_VALIDATION_REPORT.md) |
| Code coverage report | [`CODE_COVERAGE_REPORT.md`](docs/reports/CODE_COVERAGE_REPORT.md) (browsable: `docs/reports/coverage-html/index.html`) |
| Branch coverage report | [`BRANCH_COVERAGE_REPORT.md`](docs/reports/BRANCH_COVERAGE_REPORT.md) |
| Updated test cases | [`TEST_CASE_DOCUMENT.md`](docs/reports/TEST_CASE_DOCUMENT.md) |

The earlier QA register and Sprint 2 summary are in `docs/qa/`, the load test in `docs/performance/`
and the demo videos in `docs/demo/`. Differences from the SRS, SAD and Test Plan are in
[`DEVIATIONS.md`](DEVIATIONS.md).

## Workflow

1. Each backlog item is a GitHub issue on the **HMS Team 1 - Agile Project** board.
2. Create a branch per issue: `feature/<issue-number>-<short-name>`.
3. Raise a pull request with `Closes #<issue-number>`; CI must pass.
4. A repo owner reviews and merges.
5. Any deviation from the SRS, SAD or Test Plan is recorded in [DEVIATIONS.md](DEVIATIONS.md).
