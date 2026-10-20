# Hostel Management System

Team 1 Software Engineering Project.

| SRN | Name | GitHub |
|---|---|---|
| PES2UG24CS571 | Vaishnavi Goyal | whyshoee |
| PES2UG24CS582 | Vignesh Nunna | Greninja34 |
| PES2UG24CS595 | Vishnu S R | vishnusr594-afk |
| PES2UG24CS615 | Yellala Sai Aneesh Reddy | saianeesh-debug |

Design documents: [SRS](PES2UG24CS571_582_595_615_Team1_SRS.pdf) ·
[SAD](PES2UG24CS571_582_595_615_Team1_SAD.pdf) ·
[Test Plan](PES2UG24CS571_582_595_615_Team1_Software_Test_Plan_Final.pdf) ·
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
the admin site, and any other role limits them to the portal. Screens planned for a later sprint
already appear in the navigation and open a "Coming in Sprint N" page naming their backlog issue.
When a feature is built, point its entry in [`hms/navigation.py`](hms/navigation.py) at the real
view and the sidebar, dashboard cards and breadcrumbs update with it.

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
| `apps/audit` | Audit Service | HMS-SR-004 |

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

The app connects to the `hms` database as user `hms` on localhost. To use different
settings, set the `POSTGRES_*` environment variables listed in `.env.example`.

## Running checks and tests

```bash
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

GitHub Actions runs the same steps, against PostgreSQL, on every pull request to `main`.

## Workflow

1. Each backlog item is a GitHub issue on the **HMS Team 1 - Agile Project** board.
2. Create a branch per issue: `feature/<issue-number>-<short-name>`.
3. Raise a pull request with `Closes #<issue-number>`; CI must pass.
4. A repo owner reviews and merges.
5. Any deviation from the SRS, SAD or Test Plan is recorded in [DEVIATIONS.md](DEVIATIONS.md).
