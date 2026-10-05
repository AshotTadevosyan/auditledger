# Render deployment and recovery

This repository is prepared for deployment; nothing is deployed by these changes. Do not create/sync the Blueprint or trigger a deploy until the owner explicitly requests it. `autoDeployTrigger: "off"` disables commit-triggered deploys; creating or syncing a Blueprint can still provision resources and deploy.

## Architecture and access

`render.yaml` defines one paid Python web service and PostgreSQL 17 in Frankfurt. Confirm region, plan availability, cost and data residency before provisioning. Build installs pinned dependencies and collects static assets; pre-deploy applies migrations and runs Django's deployment checks; Gunicorn starts two workers. No seed data, user creation, database reset or restore runs automatically. PostgreSQL is durable; the web service filesystem is disposable. Database external access is disabled with `ipAllowList: []`.

Local operation remains loopback-only and uses the existing `data/audit.sqlite3` and `data/secret.key`. Install the updated requirements and run `migrate` after taking a backup. No existing ledger rows are rewritten by these migrations. SQLite retains its scope triggers. PostgreSQL uses composite foreign keys and immutable-scope triggers, including direct SQL writes; engagement row locks serialize workflow changes and sequence locks protect generated codes.

Hosted mode requires a secret and a PostgreSQL URL and fails at startup if either is absent. Render cannot select local mode. Hosted HTTP access requires login except `/accounts/login/`, `/accounts/logout/`, `/healthz/` and packaged static files. New accounts have no engagement access. A viewer can read and export assigned engagements; an editor can also create/edit records, transition state, delete eligible drafts and append progress. Membership applies to every engagement URL, including history and exports, and dashboard counts/owner filters. Unassigned engagements return 404. Only superusers can see all engagements. Staff status alone grants nothing. The `ledger.add_engagement` permission allows new engagements; their creator receives editor membership atomically.

Accounts and grants are managed only through an administrator shell, with no public registration or web admin. Authenticated actor labels are taken from `user:<id>:<username>`; submitted actor/author values are ignored. Existing history retains its original self-asserted labels. Reviewer, owner and verifier fields remain business assertions, not independent approval identities. Superusers, shell operators and database administrators are trusted administrators; this is not a tamper-proof audit log or a separation-of-duties system. Django password authentication does not include MFA or login throttling; apply organization-required identity/edge controls before broader exposure.

## Configuration

| Variable | Hosted behavior |
| --- | --- |
| `AUDIT_MODE` | `hosted` in the Blueprint; defaults to hosted on Render and local elsewhere |
| `AUDIT_SECRET_KEY` | Render-generated 256-bit secret, normalized with SHA-256 for Django; must be at least 32 random characters if supplied manually. Keep stable across deploys |
| `DATABASE_URL` | Private Render database connection string; PostgreSQL only |
| `AUDIT_DB_SSLMODE` | `require` on hosted connections; use `disable` only for disposable local PostgreSQL without TLS |
| `AUDIT_ALLOWED_HOSTS` | Comma-separated exact hosts; Render's `RENDER_EXTERNAL_HOSTNAME` is automatically added; never `*` |
| `AUDIT_CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins for explicitly trusted cross-origin form submission; same-origin Render forms need no entry |
| `AUDIT_TIME_ZONE` | `UTC` in the Blueprint; choose the intended audit timezone before use |
| `AUDIT_DB_PATH` | Local SQLite only; ignored when `DATABASE_URL` is set |

`DEBUG` stays false. Hosted sessions/CSRF cookies are Secure, session cookies are HttpOnly, HTTPS redirects and HSTS are enabled. The health path is exempt from redirect and checks `SELECT 1`, returning generic 200/503 JSON. Only use hosted mode behind a trusted TLS proxy that strips/replaces `X-Forwarded-Proto` (Render does TLS termination); do not expose Gunicorn directly. HSTS includes subdomains/preload, so use a dedicated HTTPS hostname. Requests validate the Host header. WhiteNoise serves collected, compressed, hashed assets; no Django development static route is used. Access logs are disabled in Gunicorn to avoid logging audit searches; review provider log access/retention separately.

## First deployment — only after explicit approval

1. Back up the local source as below. Commit reviewed code, push to the intended repository/branch, then create a Render Blueprint from the root `render.yaml`. Use separate staging resources for rehearsal. Blueprint creation can incur charges and starts deployment.
2. Review both resource plans and region, the generated secret and database binding. Do not use real audit data in preview environments. The first migration creates an empty database; it does not upload local data.
3. Wait for build, pre-deploy checks and `/healthz/` to pass. In the web service's Render shell, run `python manage.py createsuperuser`. Choose a unique strong password interactively; never put passwords in the Blueprint or source control.
4. If carrying local data forward, follow the transfer procedure below before granting accounts access. Otherwise create the first engagement as the superuser.
5. Create accounts and grants in the Render shell:

   ```sh
   python manage.py create_account auditor
   python manage.py grant_access auditor ENG-0001 viewer
   python manage.py grant_access auditor ENG-0001 editor
   # Optional new-engagement creation permission at account creation:
   python manage.py create_account lead --can-create-engagements
   ```

6. Verify in separate signed-in and signed-out browser sessions: HTTPS redirect, login, POST logout, static CSS/JS, only assigned engagements, viewer write rejection, editor save, report/export and history. Check that hidden engagement identifiers cannot be accessed directly. Confirm `/healthz/` returns 503 during a staging database outage.
7. Assign backup ownership, encrypted off-service storage and a tested retention schedule. Schedule Django `clearsessions` periodically from an operator job. Set alerts for database storage, failed health checks, backup failures and 5xx errors. Keep automatic deployment off unless explicitly approved later.

For a custom domain, configure it in Render, add its exact hostname to `AUDIT_ALLOWED_HOSTS`, and verify HTTPS and CSRF behavior before sharing the URL. Do not trust all hosts or origins.

## Preserve and transfer an existing local ledger

Stop local writes during cutover. Keep the original SQLite file and local key untouched, and use a new backup filename. A SQLite backup is not a PostgreSQL dump; do not point PostgreSQL at it or overwrite a destination that already contains audit work.

```sh
python manage.py backup_audit backups/pre-render.sqlite3
# Migrate a copy, not the source database.
python manage.py restore_audit backups/pre-render.sqlite3 data/render-transfer.sqlite3
AUDIT_DB_PATH=data/render-transfer.sqlite3 python manage.py migrate --noinput
AUDIT_DB_PATH=data/render-transfer.sqlite3 python manage.py verify_audit
AUDIT_DB_PATH=data/render-transfer.sqlite3 python manage.py dumpdata ledger \
  --exclude ledger.engagementmembership --indent 2 --output backups/ledger-transfer.json
```

Run these local commands with `DATABASE_URL` unset and `AUDIT_MODE=local`. The ledger fixture preserves UUIDs, codes, code sequences, timestamps, progress and activity events. It excludes memberships deliberately: local records did not establish hosted authorization. If transferring an already authenticated installation, use the full PostgreSQL backup/restore procedure to retain accounts and grants instead.

Transfer the fixture through a private, access-controlled operator channel. One option is a trusted workstation configured with the **new** Render database's external connection URL and a temporary allowlist entry limited to that workstation's IP. This requires explicit operational authorization; remove the entry after the transfer. Keep URLs/passwords out of command history and logs. Do not commit or publish the fixture. Alternatively, use a private operator machine on Render's network.

Against the empty, migrated destination (with `DATABASE_URL` and hosted variables set):

```sh
python manage.py loaddata /private/path/ledger-transfer.json
python manage.py verify_audit
```

Do this before users begin work. Do not rerun `loaddata` against a live populated database because it can update matching primary keys. Compare every model's row count, UUID/code/version/timestamp values, relationships and representative reports/exports with the frozen source, including Unicode and activity history. Create memberships explicitly and test access. Preserve source backups until recovery has been rehearsed and cutover accepted. Do not resume writes in both systems; rollback to the local source would omit any later hosted changes.

## Backups and recovery

For local SQLite, existing `backup_audit` and `restore_audit` remain supported and never overwrite a destination. `backup_audit` refuses PostgreSQL with guidance to use `pg_dump`. `restore_audit` only restores SQLite files and never changes the configured database. Run `migrate`, `verify_audit` and inspect reports on the restored copy before changing `AUDIT_DB_PATH`.

For PostgreSQL, use Render's managed recovery/export facilities and independently retained encrypted logical backups. From an authorized machine with PostgreSQL 17 client tools and a secure `PGSERVICE`/`.pgpass` configuration (the file must be mode 0600), use a new output filename:

```sh
pg_dump --dbname=service=audit_primary --format=custom --no-owner --no-acl \
  --file=audit-pre-upgrade.dump
pg_restore --list audit-pre-upgrade.dump > audit-pre-upgrade.contents
```

Store the dump, checksum, UTC timestamp, code commit, migration list and record counts outside the web service filesystem. Protect these as audit data and credentials: full backups contain password hashes, sessions and grants. Listing a dump is not a recovery test.

Restore into a **new empty database**, never over the live one. Use a recovery environment with the same code revision as the backup. `pg_restore` creates the schema, so do not run `migrate` on the empty target first:

```sh
pg_restore --dbname=service=audit_recovery --no-owner --no-acl \
  --single-transaction --exit-on-error audit-pre-upgrade.dump
# Point a separate app/check process at the recovery database:
python manage.py migrate --noinput
python manage.py verify_audit
python manage.py check --deploy --fail-level WARNING
# Invalidate restored sessions before opening access:
python manage.py shell -c 'from django.contrib.sessions.models import Session; Session.objects.all().delete()'
```

Verify account login, grants, model counts, histories, reports and exports in isolation. For cutover, stop writes, take a final backup, switch the service's database binding/secret configuration deliberately, deploy the compatible code and recheck health and authorization before reopening access. Record the recovery point and any lost post-backup writes. Reconcile the Blueprint binding too, so a later sync cannot reconnect the old database. Keep the original database until recovery is accepted.

A Render code rollback does not undo database migrations or recover data. If a pre-deploy migration fails, investigate and restore/rehearse against a separate database; do not fake migrations or delete data to make deployment pass. Keep old and new code compatible with schema during rolling deployment. This release adds tables/constraints and preserves existing ledger data. Do not reverse authorization migrations on a live hosted service. Roll back a failed local upgrade by switching to the preserved SQLite backup copy and matching code.

For account recovery, use `python manage.py changepassword USERNAME` from the trusted shell. Revoke a grant with `grant_access USERNAME ENG-0001 revoke`; requests recheck membership immediately. Disable a compromised account with `User.is_active=False` from an operator shell and invalidate sessions. Secret rotation logs out all users; update all instances together. Database credential rotation must update the Render binding and be tested before retiring the old credential.

## References

Configuration follows [Render's Django guide](https://render.com/docs/deploy-django), [Blueprint reference](https://render.com/docs/blueprint-spec), [health checks](https://render.com/docs/health-checks), [Django's deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) and [WhiteNoise's Django integration](https://whitenoise.readthedocs.io/en/stable/django.html). Plans and provider behavior should be rechecked when deployment is requested.
