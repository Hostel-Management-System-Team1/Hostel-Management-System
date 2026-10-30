# Issue #7 — Overdue Fees (HMS-F-013)

## What this patch adds

- Marks unpaid invoices `OVERDUE` when `due_date` is earlier than the current local date. An invoice remains `UNPAID` throughout its due date and becomes overdue the following day.
- Sends one reminder message to the resident and, if available, the guardian. The guardian is placed in BCC so the two addresses are not disclosed to one another.
- Stores `Invoice.reminder_sent_at` only after successful dispatch, preventing repeated reminders. Failed email sends are logged and remain eligible for retry on the next scheduled run.
- Adds the `process_overdue_invoices` Django management command and tests for due-date boundary, reminder recipients, idempotency, paid invoices, and retry after provider failure.
- Uses the console email backend by default for development; configure SMTP environment variables for real delivery.

## Apply and verify

1. Extract this patch into the root of your existing repository, allowing the files to merge into their matching paths.
2. Activate your project virtual environment and install the dependencies from the repository's requirements file.
3. Apply the migration:

   ```powershell
   python manage.py migrate
   ```

4. Run the focused tests:

   ```powershell
   python manage.py test apps.fees.tests.OverdueInvoiceTests
   ```

5. Run the full project checks:

   ```powershell
   ruff check .
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test
   ```

6. Test the command manually:

   ```powershell
   python manage.py process_overdue_invoices
   ```

   In development, Django prints email messages to the terminal. It does not send real email unless SMTP is configured.

## Scheduling and email

Schedule `python manage.py process_overdue_invoices` daily at 00:00 using cron or the deployment scheduler. The host's scheduled time should use `Asia/Kolkata`, matching `TIME_ZONE` in Django settings.

For real email, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and provide `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL` in the untracked `.env`. Do not commit credentials.

## Validation results

The following checks were completed successfully:

- `python manage.py migrate` — successful.
- `python manage.py test apps.fees.tests.OverdueInvoiceTests` — 5 tests passed.
- `python manage.py check` — no issues identified.
- `python manage.py makemigrations --check --dry-run` — no changes detected.
- `python manage.py test` — all 265 tests passed.

The full test suite was executed using PostgreSQL 18 on Windows.
