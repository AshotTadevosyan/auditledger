# Audit Ledger — Defect Remediation Instructions

An independent review of Audit Ledger identified the defects below. Correct them in the existing application, add meaningful regression tests, and verify the complete workflow.

- **Repository:** https://github.com/AshotTadevosyan/auditledger
- **Reviewed commit:** `d827fa1c5b5a2fd97704884e9b0527faba4f1abc`

First read `AUDIT_LEDGER_BUILD.md`, `README.md`, `VERIFICATION.md`, applicable `AGENTS.md` instructions, and the current implementation. Inspect changes since the reviewed commit. Reproduce each issue against current code before changing it; if already fixed, verify the fix with an appropriate regression test.

Preserve existing work and real audit data. Use isolated fictional databases for testing. Do not reset databases, rewrite the application, or introduce features explicitly deferred by the original brief. Keep Django, server-rendered templates, and SQLite.

Implement the following fixes in priority order.

## 1. HIGH: Protect resolved findings against changes to their linked tests

### Reproduced behavior

1. Complete an action and resolve its finding.
2. Reopen the original test linked to that finding.
3. Materially rewrite its work performed and conclusion, changing ineffective to effective.
4. Complete the test and engagement again.
5. The finding remains resolved without revalidation; the report can be marked completed.

**Relevant code:** `ledger/services.py`, particularly `transition()`, `save_record()`, and `readiness()`.

### Required behavior

- A resolved finding’s supporting test must not be reopened or materially changed until the affected finding is explicitly reopened.
- Identify every blocking finding in the error and provide actionable guidance.
- Preserve the existing requirement to reopen a completed engagement first.
- Apply these rules server-side, not only through hidden UI controls.
- For new follow-up testing, retain the original execution and use a separate test.
- Failed operations must leave records, versions, relationships, and history unchanged.

Test multiple findings sharing a test, including a mixture of open and resolved findings. Verify the permitted reopening sequence and subsequent resolution.

## 2. MEDIUM: Protect supporting evidence used by completed remediation actions

### Reproduced behavior

1. Complete an action with separate supporting and closure references.
2. Change the supporting reference’s source.
3. The reference becomes unreviewed, but the action remains completed and readiness reports no blocker.

**Relevant code:** `ledger/services.py`, `evidence_dependencies()`.

### Required behavior

- Protect both supporting and closure references used by completed actions against substantive changes and review invalidation.
- Require the appropriate dependent records to be reopened first.
- Continue allowing harmless title-only corrections according to existing rules.
- Preserve restricted deletion behavior.
- Account for references shared by several dependent records.

Test source changes, review resets, title-only corrections, and the valid reopening path.

## 3. MEDIUM: Preserve unsaved-change warnings after rejected saves

### Reproduced in the browser

1. Enter a finding narrative but omit its required title.
2. Submit the form.
3. The validation error retains the narrative.
4. Click Report: navigation occurs without an unsaved-changes warning.

**Relevant code:** `ledger/static/ledger/app.js` and form templates/views.

### Required behavior

- A rejected form containing unsaved submitted values must remain marked dirty on rendering.
- Cover ordinary validation errors, stale-version conflicts, and handled database-save failures.
- Warn before navigation or closing/reloading while unsaved changes remain.
- Clear the dirty state after successful persistence or explicit discard.
- Avoid unnecessary warnings on untouched forms and successful saves.
- Preserve entered values and existing error accessibility.

Add a browser-level regression check. Do not rely only on checking whether a data attribute exists.

## 4. MEDIUM: Detect stale control procedures when creating tests

### Reproduced behavior

1. Open Add test from a control; the procedure is prefilled.
2. Change the control’s procedure in another tab.
3. Submit the untouched original test form.
4. The new test silently stores the old procedure.

**Relevant code:**

- `ledger/views.py`: `edit()` procedure prepopulation.
- `ledger/services.py`: `save_record()` copies the stored procedure only when the submitted snapshot is empty.

### Required behavior

- Track the source control/version used to populate a new test.
- Detect a changed source before creating the test and require explicit reconciliation.
- Preserve the auditor’s submitted input.
- Do not silently overwrite deliberately customized procedures.
- Handle changing the selected control so an old control’s default procedure cannot silently become another control’s snapshot.
- Keep existing test snapshots unchanged when a control is edited later.
- Preserve the service’s safe default when no custom procedure is supplied.

Test the normal path, stale source, deliberately customized procedure, changed selected control, and service-level creation.

## 5. MEDIUM: Improve relationship selection and contextual finding creation

### Observed problems

- Test choices look like “TST-0001 · [completed]” without control, date, or result.
- The finding form lists all engagement tests with little selection context.
- An auditor must navigate away from a test and manually rebuild its relationships to raise a finding.

### Required changes

- Label test choices with code, control code/title, execution date, and result/status.
- Make finding test selection understandable in relation to selected controls, preserving server-side validation and submitted values.
- Add a contextual Raise finding action from a test that prefills its control/test relationships and offers its evidence as initial support.
- Do not create or open a finding automatically.
- Keep all relationships engagement-scoped.
- Add related-control links to the findings register, as required by the brief.
- Group drafting, supporting relationships, and closure fields sensibly.
- Show due-date-change guidance only where relevant.
- Do not offer editing/lifecycle actions that the parent finding’s state makes unavailable without explaining the required reopening step.

Keep these changes small and server-rendered; do not introduce a SPA.

## 6. MEDIUM: Remove avoidable relationship-query growth

### Independent measurements on an isolated fixture

| Fixture | Overview queries | Report-builder queries |
| --- | ---: | ---: |
| Two controls and three evidence references | 37 | 73 |
| Same engagement with 103 references | 537 | 1,073 |

**Relevant code:** `evidence_usage()`, `readiness()`, and `build_report()`.

### Required changes

- Batch or prefetch relationships and reuse engagement-level usage maps.
- Avoid repeated per-reference queries across the five evidence relationships.
- Preserve shared readiness rules, deterministic ordering, and a consistent report snapshot.
- Do not sacrifice transactional correctness for lower query counts.
- Add a representative query-growth regression test and report before/after measurements.
- No external cache, background queue, or database replacement.

## 7. MEDIUM: Make report presentation deliberate and easier to review

Current reports assemble stored data correctly, but largely enumerate model fields, show irrelevant empty lifecycle fields, separate related controls/tests, and append extensive raw JSON history.

**Relevant code:** `ledger/reports.py` and `ledger/templates/ledger/report.html`.

### Required changes

- Keep the shared report data builder and all required export content.
- Define explicit presentation fields rather than automatically exposing every future model field.
- Add a compact control–test–result–finding traceability summary.
- Make finding/action grouping clear.
- Distinguish “not applicable in this lifecycle state” from genuinely missing required information.
- Render activity changes readably while preserving their information and the complete machine-readable CSV/history export.
- Preserve draft/incomplete labels, readiness warnings, retired controls, withdrawn/resolved findings, evidence sources, progress, and closure details.
- Do not silently omit records or narrow reports using register filters.
- Preserve HTML/Markdown escaping, CSV formula protection, and safe filenames.
- Verify long narratives and long reference strings in print preview.

Do not add a custom report designer, AI summaries, or fabricated conclusions.

## Implementation and verification requirements

- Add regression tests that reproduce the defects, then confirm the fixes.
- Test both valid operations and denied operations with no partial writes.
- Keep mutations and history atomic and preserve optimistic concurrency.
- Use additive, data-preserving migrations only if necessary.
- Test migrations against an isolated copy of an existing database if schema changes are introduced.
- Run the following commands using the project’s configured Python environment:

  ```sh
  python manage.py check
  python manage.py makemigrations --check --dry-run
  python manage.py test
  python scripts/verify_end_to_end.py
  python -m pip check
  ```

- Run relevant existing lint/build/type checks if configured.
- Exercise the workflow through real HTTP/browser interactions, including:

  **Engagement → Control → Test → Reviewed evidence → Exception → Finding → Remediation → Progress/management response → Verification → Resolution → Report**

- Verify completion, reopening, dependency protection, restart persistence, and backup/restore.
- Update `README.md` and `VERIFICATION.md` to reflect behavior and checks actually performed.
- Report any verification you could not perform accurately.

## Scope boundaries

Keep the local, single-operator MVP. Do not add hosting, authentication, SSO, collaboration, uploads, integrations, numerical risk scoring, AI features, or enterprise GRC functionality. The absence of these features was intentional.

A dedicated management-response feature is not required for this repair pass; preserve the existing progress-based workflow.

Proceed autonomously with reversible implementation decisions. Do not stop at a plan or after fixing only the first issue. Do not deploy or publish anything.

## Completion report

At completion, provide:

1. Each defect and its implemented fix.
2. Regression tests and their results.
3. Before/after query measurements.
4. Browser and report/print verification results.
5. Any migrations and data-compatibility implications.
6. Remaining limitations or unresolved issues.

Do not claim the application is production-ready merely because its tests pass.
