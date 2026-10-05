# Audit Ledger

A local IT audit workspace with persistent engagements, controls, test executions, evidence **references**, findings, remediation, readiness checks and reports. Runs offline after installing its three pinned Python dependencies. There are no external APIs, uploads, email, framework catalogs or paid services.

## Start here

Python **3.10–3.14** is supported by Django 5.2; this build was executed with **Python 3.13.3** on macOS. Use an up-to-date patch release of Python. The application uses Django 5.2.17, SQLite, Django templates and plain CSS/JavaScript. No Node, Docker or separate database service is required.

From this repository directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Optional: edit .env for your timezone/database location, then load it:
set -a
source .env
set +a
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Open **http://127.0.0.1:8000/**. Stop the server with **Ctrl+C**. Start it again with the same environment and database path to resume your work. Do not seed a working database unless you want fictional demo records.

On Windows, use `py -m venv .venv` and `.venv\Scripts\Activate.ps1`; set the environment variables through PowerShell rather than sourcing `.env`. The application itself is portable, but Windows browser/OS behavior has not been manually verified.

### Optional fictional demonstration

```sh
python manage.py seed_demo
```

This explicit, repeat-safe command creates `DEMO-2026` with two controls, three reviewed reference types, effective/ineffective tests, an open high finding and an overdue action. Existing `DEMO-2026` is left untouched. Demo content never appears automatically, and the empty database has its own workflow prompts.

To keep fictional data separate:

```sh
AUDIT_DB_PATH=data/demo.sqlite3 python manage.py migrate
AUDIT_DB_PATH=data/demo.sqlite3 python manage.py seed_demo
AUDIT_DB_PATH=data/demo.sqlite3 python manage.py runserver 127.0.0.1:8001
```

## Using the workspace

1. Create an engagement with its code (or use a generated one), title, client/unit, owner and audit period. Add scope and objectives to activate it.
2. Add controls with their owners, descriptions, risks, optional framework references and testing procedures. Add tests from the control detail. A test copies the current stored procedure at creation and retains that snapshot.
3. Register evidence locations/IDs and record review decisions. Reference pickers are restricted to the current engagement and display review status. Open only validated HTTP(S) links; document paths and external IDs are copyable text. No target is fetched, read, uploaded or verified by the server.
4. Save each test's execution details and result, then complete it through its lifecycle action. Effective, partially effective and ineffective results require reviewed support; not-applicable and unable-to-conclude results require an explicit rationale.
5. Create draft findings, progressively complete narratives and support, then open them. If a cause is unknown, explicitly explain that. Severity is qualitative and requires a rationale. For failed tests, link an open/resolved finding or document why no finding is raised.
6. Add actions to open findings, with an owner and due date. Append dated progress; changing the due date requires a reason. Submit finished work for verification, save closure details/references, then mark the action completed. Resolve the finding separately with its own verification and closure evidence.
7. Use Overview readiness links to finish missing work. Enter review, then explicitly complete the engagement. Open findings are permitted at completion when they have valid assigned actions; all outstanding and overdue work appears in the report.
8. Use Report for Markdown, a CSV ZIP, or Print / Save as PDF. Exports always include the entire engagement, regardless of register filters. Incomplete exports display **DRAFT / INCOMPLETE** and omissions.

Completed records require an explicit reason to reopen. Completed engagements must be reopened first. In-review engagements also require a reason to return to active before editing. Archive is separate and reversible; only draft/completed engagements can be archived. Retiring controls retains their history and findings. Withdrawal retains findings and their reason; actions on a withdrawn finding require the finding to be reopened before they can be changed.

The dashboard and registers include search, filters, deterministic ordering and 20-row pagination. Each engagement has Overview, Controls & Tests, Evidence, Findings, Remediation, Report and History navigation. Failed saves retain submitted input and report errors. A stale version returns a conflict; open the current record in another tab, copy/reconcile your changes, and reload the form before saving. Forms warn before discarding unsaved input.

## Configuration and local operating assumptions

`.env` is a shell environment example, **not automatically loaded** by Django. Load it as shown above each time, or configure your shell/service environment. Relative database paths resolve against the repository root.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUDIT_DB_PATH` | `data/audit.sqlite3` | Persistent SQLite path, outside static assets |
| `AUDIT_SECRET_KEY` | Generated private `data/secret.key` | Optional explicit secret; never commit a real key |
| `AUDIT_TIME_ZONE` | `UTC` | IANA timezone, e.g. `Asia/Yerevan`; date boundaries and display |
| `AUDIT_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated hosts; keep these loopback-only |

The example environment chooses `Asia/Yerevan`. Timestamps are persisted in UTC. Audit periods and due dates may be future dates; completed collection/execution/review/verification dates may not. Due today is **not overdue** in the configured timezone.

**No authentication is implemented. This is a single-operator, loopback-only application.** The UI discloses this, and middleware rejects non-loopback peer addresses. Bind the server to `127.0.0.1`, never `0.0.0.0`. Do not put this app behind a public/LAN reverse proxy: a local proxy can make remote traffic appear to originate on loopback.

CSRF checks, safe host defaults, same-origin forms, a restrictive Content Security Policy, escaped templates, no-store responses and foreign keys are enabled. Normal request access logging is disabled to avoid logging sensitive search terms. No CORS permission is granted. Keep the machine, account and database location access-controlled. The app sets a restrictive process umask, creates its data directory with mode 0700 and new data/backup files with restrictive permissions. Existing directories retain their permissions; secure any custom location yourself.

Storage, backups and exports are **not encrypted by the application**. Local operation does not protect data from other processes/users with filesystem access. Owners/reviewers are self-asserted text labels and are not authenticated identities. The activity log is application history, **not tamper-proof logging**: database administrators can change it, and restores can roll it back. This software does not certify regulatory compliance, document integrity or assurance.

A network or multi-user deployment requires a separately designed authentication/authorization model, engagement membership enforced on every record and export, HTTPS, production serving/session settings and operational backup ownership. These are deliberately outside this local MVP.

## Data integrity and implementation decisions

The supplied workspace initially contained only `AUDIT_LEDGER_BUILD.md`, without manifests, application files, migrations, tests or applicable `AGENTS.md`. The GitHub repository `AshotTadevosyan/auditledger` returned no refs, and cloning confirmed an empty repository. No existing implementation was replaced. The brief's Django/SQLite fallback was followed. Django's [5.2 release documentation](https://docs.djangoproject.com/en/5.2/releases/5.2/) and [supported releases](https://www.djangoproject.com/download/) were checked before pinning dependencies.

- UUID record IDs; stable readable codes; transactional per-engagement code sequences. Deleted codes are never reused. Engagement codes are globally unique, other codes unique per engagement.
- Foreign keys use `PROTECT`, never cascade audit work. SQLite enables FK enforcement on each Django connection. Migration `0002` adds INSERT/UPDATE triggers that enforce engagement equality on every child/join row, plus immutable engagement ownership. This SQLite-specific migration is an intentional integrity choice.
- Supporting and closure action evidence use separate relationship tables, an equivalent normalized representation of the brief's purpose column. Other required relationships are separate unique-pair tables. Findings enforce that linked tests belong to their linked controls.
- `ledger/services.py` owns validation, transitions, shared readiness, optimistic versions and atomic activity events. SQLite `IMMEDIATE` transactions serialize writes before validation. Forms/requests cannot set status or protected fields directly. Relation and history changes roll back together when validation fails.
- Evidence used by completed tests, resolved findings or completed actions is protected. References supporting **open** findings are also protected against review invalidation: first replace/unlink that support while keeping the finding valid. Title-only corrections can retain review. Changes to source/type/system/description, collection date, owner or notes reset review and preserve the prior assertion in history.
- Completed tests/actions and resolved/withdrawn findings are read-only. Reopening preserves previous closure values and records their disposition in history. Completion validation is rerun on each new completion/resolve operation.
- All stored tests, including unfinished historical tests on retired controls, remain visible and must be completed before review. Retired controls are excluded from the requirement to have a completed test; their unresolved findings still participate in readiness.
- `ledger/reports.py` builds one consistent transactional snapshot for HTML/Markdown/CSV. Result counts and the latest completed result (execution date, then creation time/ID) are calculated; multiple tests are never merged into an inferred opinion.
- Titles/owner labels: 200 characters. Codes: 40. Sources/URLs: 2,048. Narrative fields, reasons and progress: 20,000. Required strings reject whitespace-only input. Model, form, service, uniqueness and database constraints complement each other.
- The UI only allows confirmed deletion of unlinked draft-like records (planned tests, draft findings, not-started actions, unreviewed references, unretired controls). Issued work uses lifecycle transitions. Engagement deletion and activity/progress editing/deletion are not exposed.

The source reference is preserved as escaped plain text in reports. Newly entered URL references must use valid HTTP(S) destinations without credentials/control characters. Legacy unsafe values, if introduced outside the application, are never rendered as executable links. Sources are never interpreted as shell commands or local-file launch actions.

### Report formats

Markdown escapes raw HTML and Markdown structural characters while preserving narrative line breaks. The CSV ZIP contains all main tables, progress updates, all relationship tables, history, an included Markdown report and `DATA_DICTIONARY.txt`. CSV tables include stable IDs, codes, ISO dates, versions and export metadata; empty tables retain headers. Files use UTF-8 with BOM for spreadsheet interoperability.

A leading apostrophe neutralizes formula-like CSV values beginning with `=`, `+`, `-` or `@`, including after whitespace/control characters, and cells starting with tabs/newlines. This protective prefix is **export-only**, is documented in the dictionary and is not stored in the database.

Report filenames use a sanitized code and generation date. Downloads are generated on request and never saved into public assets. Reports are regenerated views, not signed/frozen export artifacts. Browser Save as PDF pagination varies by browser/printer settings.

## Tests and verification

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 2
python scripts/verify_end_to_end.py
python -m pip check
```

The end-to-end script needs permission to bind a loopback port. It uses temporary on-disk databases and actual HTTP requests with cookies and CSRF tokens. It creates the complete workflow from an empty database, stops/restarts the server, compares every persisted table, completes with outstanding remediation, rejects edits to completed work, reopens and verifies closure, checks Markdown/CSV/HTML, attempts cross-engagement access, backs up while running, restores into a new path and starts a server against the restored database. It leaves your working database untouched.

The automated suite covers validation, uniqueness, dates/timezone boundaries, invalid transitions, evidence protection/review reset, closure prerequisites, version conflicts, history rollback, foreign-key/scope enforcement, deletion, all page rendering, HTTP forms, CSRF/local-host restrictions, CSV quoting/formula protection, Unicode/HTML/Markdown escaping and empty exports.

See [VERIFICATION.md](VERIFICATION.md) for the checks actually performed and manual verification scope. Tests cover the local MVP; they are not a security certification or a multi-user assessment.

## Backup, restore and upgrades

Use the supported SQLite backup API, **not a live copy of the main SQLite file** (which may omit WAL transactions). Choose a new path each time. Existing databases/backups are never overwritten.

```sh
python manage.py backup_audit backups/audit-2026-10-04-1800.sqlite3
```

The command verifies SQLite integrity/foreign keys and writes a companion `.sqlite3.manifest.json` containing the app version, committed migration names, UTC backup timestamp and record counts. It is safe to run while the application is active. It can briefly contend with writes; the database timeout is 15 seconds. Store the verified backup on a separate access-controlled device/location. Choose retention and encryption according to the engagement. A practical schedule is before upgrades and at the end of active audit work.

Restore with the app stopped, into a **new** path, while preserving the current database:

```sh
# Stop runserver with Ctrl+C first.
python manage.py restore_audit backups/audit-2026-10-04-1800.sqlite3 data/restored-audit.sqlite3
AUDIT_DB_PATH=data/restored-audit.sqlite3 python manage.py migrate
AUDIT_DB_PATH=data/restored-audit.sqlite3 python manage.py verify_audit
AUDIT_DB_PATH=data/restored-audit.sqlite3 python manage.py runserver 127.0.0.1:8001
```

Inspect engagement counts, related tests/evidence, action progress, dispositions and the report at http://127.0.0.1:8001/. Compare the backup manifest. Only after verification should you stop this test server and change `AUDIT_DB_PATH` in your normal environment to the restored path. Keep the original database and backup until you are satisfied. Restore with the same app version first, then apply compatible forward migrations; never downgrade code against a newer schema. The repository migrations recreate the scope-enforcement triggers on fresh databases.

For upgrades:

```sh
# Back up first; stop the running application before changing dependencies/schema.
python manage.py backup_audit backups/pre-upgrade-2026-10-04.sqlite3
# Obtain the intended new source version through your normal Git workflow.
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py verify_audit
python manage.py runserver 127.0.0.1:8000
```

If a backup/restore command fails, it reports failure; a partial destination may remain for diagnosis and will not be reused automatically. Pick a fresh destination after resolving the problem. The included end-to-end test performs an actual independent restore and report check; a backup is not proven usable just because a file exists.

## Known boundaries

Local, single-user operation is the delivered product. Attachments, integrations, invitations, SSO, email, framework libraries, AI summaries, immutable retention, approvals/signatures, numeric risk scoring and hosted collaboration remain deferred as specified. SQLite-specific scope triggers mean migration to another database backend needs equivalent constraints and tests. Large engagements are paginated in registers, but whole-engagement readiness/export evaluation intentionally reads all records and briefly holds a consistent database transaction; performance at enterprise-scale volumes has not been benchmarked. The print appendix includes activity before/after values and can become lengthy.

## Remediation safeguards and regression checks

Resolved findings protect every linked test, including unfinished tests. To rework an execution, reopen the completed engagement first, then **every resolved finding listed in the error**, then the completed test. Re-completion and resolution rerun validation. For new follow-up work, add a separate test and retain the original execution. Completed actions protect both supporting and closure references; reopen the parent finding when resolved, then every dependent completed action/test before changing the source or resetting review. Open-finding support must still be replaced/unlinked without invalidating the finding. Title-only evidence corrections retain review; linked deletion remains restricted.

Add test from a control records the prefilled source control and version in the form. A changed source or selected control returns a conflict with the submitted procedure retained. Compare the current selected control in another tab, reconcile the snapshot, and explicitly confirm the comparison before saving. Deliberately customized procedures are retained. Service calls without a custom procedure still copy the current stored control procedure inside the write transaction; later control changes do not change existing snapshots.

Test relationship choices include control code/title, execution date, result and status. **Raise finding** on a test opens an unsaved draft with its control/test and evidence preselected; it does not create or open a finding. Findings-register control links provide context. Drafting, relationships and closure fields are grouped. Remediation under a non-open finding explains the required reopening step and does not offer unavailable actions.

Rejected validation, stale-version and handled database-error forms retain navigation/reload warnings. A successful save clears unsaved state; confirming discard permits navigation. Reports use explicit presentation fields, a control–test–result–finding summary, finding-grouped remediation and readable before/after history. Empty lifecycle fields that do not apply are grouped separately from missing information. CSV tables and JSON history remain complete. Readiness and the report builder reuse batched relationships without an external cache.

The optional real-browser regression uses installed Google Chrome on macOS, a temporary fictional database and a test-only injected database failure. Its dependencies are separate from the application's runtime requirements:

```sh
python -m pip install --target /tmp/auditledger-browser-tools playwright pymupdf
PYTHONPATH=/tmp/auditledger-browser-tools AUDIT_BROWSER_OUTPUT=/tmp/auditledger-browser-results python scripts/verify_browser.py
```

It checks actual confirmation/beforeunload dialogs, retained input after validation/conflict/database failures, successful saves, explicit discard, stale procedure reconciliation and contextual finding creation. It captures desktop/narrow layouts and Chrome's A4 print output. When PyMuPDF is available it checks complete long narrative/reference text, page bounds and renders pages for visual inspection. `AUDIT_BROWSER_OUTPUT` is optional; without it the temporary captures are removed after the run. These are fictional verification artifacts, not audit exports. The harness requires loopback/browser execution permissions and the installed Chrome path specified in the script. It does not alter the normal working database.
