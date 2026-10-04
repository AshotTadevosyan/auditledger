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
