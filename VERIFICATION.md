# Verification record

Executed on 4 October 2026, macOS, Python 3.13.3, Django 5.2.17 and SQLite. All automated checks used isolated test databases; the working database was not seeded.

## Automated checks

| Check | Result |
| --- | --- |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No model/migration drift |
| `python manage.py test --verbosity 1` | 35 tests passed |
| `python -m pip check` | No broken dependencies |
| `python scripts/verify_end_to_end.py` | Passed, including a second complete run after fixes |

The real-HTTP verification created engagements, controls, evidence, tests, findings and actions through CSRF-protected forms. It verified exact persisted table contents after stopping and restarting the application. It completed an engagement with overdue remediation, rejected edits while completed, reopened it, verified action closure and resolved the finding. It checked report formats and rejected forged cross-engagement references.

The same run created a live SQLite backup, restored it into an independent database, compared all persisted records, checked integrity and foreign keys, applied migrations and served the restored report over HTTP. This tests recovery, rather than merely checking that a backup file exists.

The Django suite also covers transactional history rollback, stale versions, database scope triggers, chronology, readiness, lifecycle prerequisites, protected deletion, evidence review invalidation, deterministic latest results, HTML/Markdown escaping, CSV formula neutralization and empty exports.

## Manual browser checks

- Safari: empty workspace and populated fictional demonstration, engagement navigation and report rendering.
- Safari: real invalid form submission retained entered values and displayed both the error summary and field errors. A same-origin referrer configuration correction was verified through an actual browser POST.
- Safari Responsive Design Mode at 390 × 844: the form and errors remained readable within the viewport; focus styling was visible.
- Long-report fixture: 45 narrative paragraphs and a roughly 1,900-character source reference, stored only in the separate fictional preview database.
- Chrome: saved the long report to a 19-page PDF before the final pagination refinement. PDFKit extracted all pages and found no text selections outside page bounds. The final narrative paragraph and complete source suffix survived extraction; rendered narrative and source-reference pages were visually inspected for clipping.
- Final print CSS: Safari's A4 preview showed 14 pages after removing forced section breaks and tightening tables. The cover and following summary were visually inspected. Safari's PDF Save button remained disabled in the available native print panel, so the final 14-page version was not independently extracted as a PDF.

## Scope and remaining limits

These checks validate the delivered local workflow. They do not establish authenticated identity, tamper-proof history or regulatory compliance. No multi-user/network deployment, enterprise-volume benchmark, full screen-reader audit, physical mobile device, Windows/Linux browser run or physical printer test was performed. Final pagination depends on browser, paper size, scaling and printer settings; inspect the preview before issuing a report.

See [README.md](README.md) for startup, configuration, workflow, backup/restore and operating boundaries. The end-to-end script is repeatable and leaves the working database untouched.

## Remediation verification — current pass

The starting tracked code matched reviewed commit `d827fa1`; there were no later commits or tracked edits. The supplied untracked `AUDIT_LEDGER_REMEDIATION.md` was preserved. No applicable `AGENTS.md` or configured lint/build/type command was found. Existing Django, server-rendered templates, SQLite, migrations and real working data were preserved. All mutation fixtures used isolated fictional databases; there are **no schema migrations or data conversions** in this change.

### Defects, reproduction and regression coverage

1. **Resolved finding / test protection:** a regression initially reopened a resolved finding's linked test successfully, demonstrating the defect. Service guards now enumerate every resolved blocker before test edits/transitions. Tests cover multiple resolved findings plus an open finding sharing one test, unfinished linked test edits, unchanged versions/relationships/history on denial, engagement-first reopening and subsequent test completion/finding resolution.
2. **Completed action support:** a regression initially changed separately linked supporting evidence without error. Both support and closure dependencies are now protected. Tests cover source changes, review resets, harmless title correction, two completed actions sharing a reference, unchanged snapshots/history after denial and the permitted reopening path. Existing restricted-deletion checks continue to pass.
3. **Rejected-form unsaved values:** the real Chrome harness fails against an isolated reviewed-commit copy because clicking Report after validation rejection navigates without confirmation. It passes on repaired code. It exercises actual confirm and beforeunload dialogs, input retention, validation errors, stale edits from a second tab, a handled database-save failure, explicit discard, untouched forms and successful saves. Error-summary focus is checked; this is not merely a data-attribute assertion.
4. **Stale procedure source:** reviewed-code HTTP reproduction accepted the old snapshot (302) after the control changed; repaired code returns 409 without creating records/history. Tests cover normal/customized creation, changed selected control, explicit reconciliation with retained custom input, current service defaults and unchanged historical snapshots. The real browser changes a control in another tab and reconciles the retained test procedure.
5. **Relationship context:** reviewed-code checks showed no contextual relationship prepopulation and uninformative test labels. Tests/browser now verify test/control preselection, meaningful labels, no finding creation on GET, findings-register control links and reopening guidance for unavailable action operations. Server-side engagement/relationship validation remains covered by the existing suite.
6. **Relationship query growth:** reproduced the independent measurements exactly, then verified bounded queries after batching. Shared readiness and complete report snapshots remain transactional; no cache was introduced.
7. **Report presentation:** explicit field lists, traceability rows, grouped remediation, compact inapplicable lifecycle fields, retained prior closure labels and readable history replace automatic field enumeration/raw JSON presentation. Regression checks cover grouping and complete machine history; existing escape/formula/Unicode/empty-export checks pass. All stored records remain in reports irrespective of register filters.

### Query measurements

Measured with Django `CaptureQueriesContext`, two controls, two completed tests, one open finding/action, and 3 versus 103 evidence references (100 additional unlinked fictional references). Overview includes HTTP rendering; report-builder counts include its transaction boundaries in the test context.

| Measurement | Before, 3 refs | Before, 103 refs | After, 3 refs | After, 103 refs |
| --- | ---: | ---: | ---: | ---: |
| Overview | 37 | 537 | 30 | 30 |
| Report builder | 73 | 1,073 | 35 | 35 |

The regression permits at most five added queries and currently observes zero growth. This is a representative relationship-growth check, not an enterprise-volume benchmark.

### Executed checks

- Configured `.venv` Python: `manage.py check` passed; `makemigrations --check --dry-run` found no changes; **47 tests passed**; `python -m pip check` found no broken requirements; `git diff --check` passed.
- `scripts/verify_end_to_end.py` passed with real CSRF-protected HTTP forms: engagement → controls → reviewed references → effective/ineffective tests → finding → remediation/progress (management response) → verification → resolution → exports.
- That script compared persisted tables after process restart; completed the engagement with outstanding remediation; denied completed-work edits; reopened and resolved work; checked scoped relationships; performed live SQLite backup, independent restore, integrity/foreign-key checks, migrations and a restored HTTP report.
- `scripts/verify_browser.py` passed in installed headless Chrome on macOS. Optional Playwright/PyMuPDF packages were installed under `/tmp`, not added to runtime requirements. Loopback/browser execution used the required environment permission; the initial sandbox-only HTTP launch was denied before the successful permitted run.
- Browser captures cover desktop and 390 × 844 widths, rejected-form accessibility focus and Chrome A4 print output. The long fixture has 45 narrative paragraphs and a 1,915-character source reference. Full narrative/source markers survive PDF extraction, with no text bounding boxes outside page bounds. All rendered pages were inspected as contact sheets, with detailed checks of traceability, action grouping and long content. The final Chrome A4 output has **39 pages**. Fictional captures and rendered pages were retained under `/tmp/auditledger-browser-results` for this session; they are not committed.

### Remaining verification boundaries

No native operating-system print dialog, physical printer, Safari/Firefox rerun, full screen-reader audit, physical mobile device, or Windows/Linux browser verification was performed in this remediation pass. Chrome's print renderer/PDF was exercised rather than claiming an OS print-preview test. Browser pagination varies. Complete before/after history can still make reports long; it is retained intentionally and remains fully machine-readable in CSV. Optional browser dependencies are not application dependencies. No hosting, deployment, authentication, AI, uploads, integrations or other deferred features were introduced. Passing checks do not establish production readiness, identity assurance or tamper-proof history.

## Authenticated Render preparation (2026-10-05)

No Render resources were created, no Blueprint was synced and nothing was deployed. The configuration was checked against current official Render/Django/WhiteNoise documentation; YAML parsing succeeded locally. Provider-side Blueprint provisioning/validation, real Render TLS routing, custom DNS and production monitoring remain deployment-time checks.

Verification performed for this change:

- Full SQLite suite: 59 tests discovered, 57 passed and 2 PostgreSQL-only concurrency tests skipped.
- Full PostgreSQL 17 suite in a disposable local Docker database: 59 tests passed, including fresh migrations, existing workflow/integrity tests and concurrent create/edit tests.
- Hosted tests cover anonymous access to every data/mutation route, login/logout and CSRF, safe login redirects, secure cookies, viewer/editor access, superuser access, immediate membership revocation, inactive accounts, hidden dashboard data, cross-engagement object IDs, forged actor/progress-author submissions, creator membership, and rollback when membership creation fails.
- Hosted configuration fails closed without required variables or if Render is forced into local mode. `check --deploy --fail-level WARNING` passed without warnings using hosted settings. Database-aware public health responses and generic outage responses were verified.
- `collectstatic` in hosted mode succeeded. With `DEBUG=False`, the login page rendered and WhiteNoise served nonempty hashed CSS and JavaScript; a data-file URL returned 404. Gunicorn's `--check-config` passed. Actual Render process startup/edge routing has not been exercised.
- `makemigrations --check --dry-run` reports no missing migrations; `git diff --check` passed.
- A temporary consistent copy of the existing `data/audit.sqlite3` was migrated and checked with `verify_audit`. Every original ledger table row compared equal before/after, and the original database file's SHA-256 was unchanged. The live local database was not migrated or replaced.
- Synthetic demo records were exported from SQLite with the documented `dumpdata` exclusions, imported into fresh PostgreSQL with `loaddata`, and checked with `verify_audit`. All serialized ledger records matched exactly. A full `pg_dump` custom archive was restored with `pg_restore --single-transaction --exit-on-error` into another empty database; migrations, relationship/report verification and the exact serialized-record comparison passed again.

Reproduce the suites with `.venv/bin/python manage.py test --noinput` for SQLite and the same command with `DATABASE_URL` pointing to a disposable PostgreSQL database for PostgreSQL. The test database user needs database-creation permission. Never point test or rehearsal commands at production. Hosted settings additionally require `AUDIT_MODE=hosted`, `AUDIT_SECRET_KEY`, and the appropriate TLS/host settings described in [DEPLOYMENT.md](DEPLOYMENT.md).
