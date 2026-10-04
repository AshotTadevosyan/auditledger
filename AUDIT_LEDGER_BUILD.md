# Audit Ledger — implementation brief

## 1. Mandate and repository context

Build **Audit Ledger**, a practical web application for an IT auditor managing audit engagements. The auditor must be able to start an engagement, define controls, collect evidence references, record findings, assign remediation, and export a coherent report without disconnected spreadsheets.

This document specifies the application to implement. It is not a claim of regulatory compliance, certification, or assurance. Framework references are user-entered context; the software must not infer compliance from a control result.

Repository supplied by the product owner: <https://github.com/AshotTadevosyan/auditledger>.

**Repository inspection limitation:** On 2026-10-04, the brief author could not retrieve the GitHub repository page, repository API response, or a candidate main-branch README through the available web tooling. No repository structure, branch, implementation, or stack has been verified. This does not establish whether the repository is private, empty, or unavailable to the implementing agent.

Before choosing a stack or changing files, inspect the actual local repository, applicable `AGENTS.md` files, README, manifests, lockfiles, migrations, tests, and working-tree changes. Preserve useful existing work and user edits. Reuse the established stack and conventions if viable. Do not replace an application merely to match the fallback stack below. Document actual findings and any justified departures from this brief.

## 2. Product purpose and MVP boundary

The primary user is an auditor responsible for recording defensible audit work and following remediation. Control owners and remediation owners are contacts recorded by the auditor in the MVP; assigning an owner does not create a login, send a notification, or give that person access.

The core journey is:

1. Establish the engagement and its scope.
2. Define the controls and how they will be tested.
3. Register evidence references and document test execution.
4. Record findings with traceable support.
5. Assign and update remediation actions.
6. Assess readiness, review a report, and export the stored work.

### Required first working version

- Persistent engagement, control, test, evidence-reference, finding, remediation, and activity records.
- Engagement-scoped navigation, usable forms and tables, search, filters, and cross-links.
- Explicit lifecycle rules, field validation, evidence relationships, and readiness checks.
- Markdown report, CSV data exports, and a printable HTML report suitable for browser Save as PDF.
- Local single-user operation, documented setup, migration management, backup/recovery, and meaningful automated checks.
- Fictional demonstration data available only through an explicit seed command; an empty database must also work.

### Defer until after the MVP

Hosted collaboration, multiple user roles, SSO, invitations, email, automated evidence collection, document uploads or previews, framework libraries, risk-scoring engines, recurring engagements, approvals/signatures, integrations, AI summaries, immutable retention, and custom report designers. Do not build these as prerequisites. A text owner field and manual progress updates are sufficient for the first version.

## 3. Audit workflow and operating rules

### 3.1 Engagement setup

Create an engagement with a readable code, title, client or business unit, scope, objectives, audit-period start/end dates, and accountable owner. Capture methodology and an auditor-written executive summary during the work. Dates must be valid and end must not precede start. Allow substantive narrative fields to be incomplete while drafting, with visible readiness warnings.

Engagement states: `draft → active → in_review → completed`.

- Draft creation requires code, title, client/business unit, owner, and valid audit period.
- Activation also requires nonblank scope and objectives.
- Moving to review requires at least one active control and a completed test for every active control; evidence linked to completed tests must be reviewed. Open findings must satisfy the finding rules below.
- Completion requires all report-readiness blockers to be resolved, methodology and executive summary supplied, and an explicit auditor confirmation with completion timestamp.
- Outstanding remediation does not prevent completing an audit report if each open finding has an action with an owner and due date. The report must show the outstanding work.
- Return from review to active or reopen completed to active with a mandatory reason. Completed engagements are read-only until explicitly reopened. Do not silently mutate a completed report's underlying data.

Archiving is a separate reversible flag, allowed for draft or completed engagements. Archived records remain readable/exportable and are excluded from default active lists. Unarchive before editing. MVP does not require engagement deletion.

### 3.2 Controls and testing

Controls contain an engagement-unique code, title, description, control owner, risks addressed, optional framework references, and testing procedure. Framework references are text/list entries such as a framework name, version, and control reference, without validation against a licensed catalog.

Each control supports multiple tests. Each test records a procedure snapshot, tester, execution date, sample or population description (including a reason if sampling is not applicable), work performed, result, conclusion, and evidence links. Updating a control's procedure must not change prior test snapshots.

Test states: `planned → in_progress → completed`; planned may move directly to completed if completion validation passes. Reopening a completed test requires a reason and returns it to in_progress. A completed test requires execution date, tester, procedure, work performed, sample description/reason, a result, and a conclusion.

Results: `effective`, `partially_effective`, `ineffective`, `not_applicable`, `unable_to_conclude`.

- Effective/partially effective/ineffective tests require at least one reviewed supporting reference.
- Not-applicable results require an applicability rationale; evidence is optional.
- Unable-to-conclude results require a documented limitation; evidence is optional, and the report displays the limitation prominently.
- Partially effective or ineffective tests require a linked open/resolved finding or an explicit auditor rationale for not raising a finding before the engagement enters review.
- Do not automatically create findings, infer assurance, or silently collapse several tests into one opinion. Display test-result counts and a derived latest completed result by execution date, then creation time/ID for deterministic ties. Label it as the latest result, not an overall opinion.

Controls may be retired with a reason while an engagement is editable. Preserve them and their tests; show retired status in reports and exclude them from active-control completion requirements. Retiring a control must not hide an unresolved finding or remove it from readiness checks.

### 3.3 Evidence-reference register

Register a title, description, reference type, exact source location/identifier, collection date, owner, and review state. Types are `url`, `document_path`, and `external_document_id`. For external IDs, require a source-system label so an identifier is understandable outside the app. Optional notes may record version, page, section, or access instructions, but never credentials.

**Registering a reference does not upload, store, fetch, verify, or preserve the underlying document.** Display this notice in the register and report appendix. A review records an auditor's assertion about their examination of a reference; it does not prove accessibility, authenticity, completeness, or integrity of its target.

Review states: `unreviewed → reviewed` or `rejected`. Reviewed requires reviewer name, review date, and a brief review note. Rejected requires a reason. A rejected reference may return to unreviewed after correction. Changes to the source, type, source system, or substantive description reset review to unreviewed and are recorded in activity history. Title-only corrections need not reset review.

A reference can support many tests, findings, and remediation actions in the same engagement. Show where it is used. Unlinked references are permitted and flagged as informational. References used by completed tests or resolved findings cannot be substantively changed or removed until the dependent records are reopened. Deletion is restricted when any relationship exists; offer unlink/reopen guidance instead of cascading loss.

### 3.4 Findings

Create a draft finding with code, title, and provisional severity; allow progressive completion. Capture condition (what was observed), criteria (what should apply), cause, impact, severity, recommendation, owner, related controls/tests, and supporting evidence references. If cause remains undetermined, require an explicit explanation instead of an empty field or invented cause.

Severity levels are `critical`, `high`, `medium`, `low`, and `informational`. Use qualitative guidance: critical means urgent substantial exposure; high means significant exposure requiring prompt attention; medium means a meaningful weakness requiring planned correction; low means limited exposure; informational means an improvement observation. Require a severity rationale. Do not introduce unapproved numeric scoring or promise automatic severity classification.

Finding states: `draft → open → resolved`, with `draft/open → withdrawn` and `resolved/withdrawn → open` permitted with a reason.

- Opening requires all finding narrative fields, severity rationale, owner, at least one related control, and at least one reviewed evidence reference. Related tests are optional but must belong to the linked controls.
- An open finding may have several remediation actions.
- Resolving requires at least one action, every action completed, a verification conclusion, verifier, verification date, and reviewed closure evidence.
- Withdrawal requires a reason and retained history. It cannot be used as a silent deletion. Withdrawn findings remain visible in exports with their disposition.
- Completed actions may only be reopened after their resolved parent finding is reopened. Reopening a finding within a completed engagement first requires reopening the engagement.

### 3.5 Remediation

Each action belongs to one finding and inherits its engagement. Capture a readable action code, description, owner, due date, status, progress updates, and closure details. Owner and due date are required from creation. Progress updates are dated entries with author and text, not a single overwritten notes field.

Action states: `not_started → in_progress → ready_for_verification → completed`. Permit not_started to ready_for_verification if work was completed outside the application. `blocked` may be entered from not_started/in_progress with a reason and returns to in_progress. Rejection at verification returns to in_progress with a reason. Completed requires verifier, verification date, closure conclusion, and at least one reviewed closure reference. Reopening completed requires a reason and preserves previous closure information in history.

Overdue is a calculated badge, not a stored lifecycle status: due date before today's configured local calendar date and action status is not completed. Due today is not overdue. Due-date changes require a reason and history. Do not auto-close findings when actions finish; the auditor makes the resolution decision.

### 3.6 Readiness and reporting

Provide a readiness panel with blockers, warnings, counts, and direct links to affected records. Share the same readiness logic between UI, transition validation, and reports.

Block review/completion for invalid required fields, active controls without completed tests, tests still planned/in progress, drafts or incomplete open findings, rejected/unreviewed references used as required support, failed-test dispositions missing, open findings without actions, or invalid closure records. Completion additionally requires methodology and executive summary. An engagement with no active controls cannot complete.

Warnings include overdue actions, outstanding remediation, unused references, and unable-to-conclude tests. Warnings do not block completion but must be visible in the report. Draft export is always available: include a prominent DRAFT/INCOMPLETE label and a list of missing information. Do not suppress incomplete records to make a report appear ready.

## 4. Screens and navigation

Use a persistent application header and engagement breadcrumb. The dashboard is the entry point; inside an engagement use tabs: Overview, Controls & Tests, Evidence, Findings, Remediation, Report, and History. Preserve the engagement context in routes and cross-links. Use simple detail pages or panels with explicit Save/Cancel, clear success/error feedback, and a warning before abandoning unsaved changes.

| Screen | Essential content and actions | Search, filters, and empty state |
| --- | --- | --- |
| Dashboard | Engagement table with code, title, client/unit, owner, period, status, open findings and overdue actions; create/open/archive controls; counts link to filtered lists | Search code/title/client; filter status, owner, archived; empty state explains the workflow and offers Create engagement |
| Engagement overview | Editable setup fields, summary/methodology, lifecycle actions, readiness panel and counts | Link each blocker to its record; a new engagement prompts Add first control |
| Controls & Tests | Control table and detail, all control fields, test history, create/edit/complete/reopen test, related findings and evidence picker | Search code/title/risk/framework; filter owner, retired, tested/untested and result; distinguish no controls from no filter matches |
| Evidence register | Type, title, source, collection date, owner, review status; create/edit/review, copy source, safe URL open, usage list | Search title/description/source; filter type, owner, status, unused; empty state explains reference-only storage |
| Findings register | Code/title, severity, status, owner, related controls, action count; full narrative editor, evidence links, lifecycle actions | Search code/title/narratives; filter severity/status/owner/control; empty state offers Add finding without implying that no findings means assurance |
| Remediation tracker | Finding link, action, owner, due date, lifecycle and overdue badges; progress timeline, closure references, verification controls | Search code/description/owner; filter status, owner, due range, overdue and finding; empty state links to findings |
| Report preview/export | Full report with readiness banners, generated-at time, Markdown download, CSV bundle and Print/Save as PDF | Preview exactly the engagement exported; do not let register filters silently remove report records |
| Activity history | Chronological events with record links, actor, time, operation, reason and changed fields | Filter entity type and operation; initial state explains when history begins |

All forms must have visible labels, sensible field ordering, required markers, inline validation and an error summary. Failed saves retain input. Evidence selectors show review status and exclude other engagements. Destructive or consequential actions name the affected record and explain consequences before confirmation. Editing ordinary fields should not require repeated confirmations.

Use a restrained professional style: neutral surfaces, one accent color, readable dense tables, wrapped long text, clear column headings and responsive overflow. Provide pagination for large registers and deterministic sorting. Status indicators must include text rather than color alone. Support keyboard navigation, visible focus, adequate contrast, semantic headings/table headers, and properly labelled dialogs. Dates display unambiguously; persisted timestamps use UTC with local display. Test layouts at desktop and narrow viewport widths. Avoid ornamental dashboards or placeholder charts.

## 5. Data model and integrity

Use relational persistent storage. Every main record has an opaque stable primary key (UUID or established repository equivalent), UTC created_at/updated_at timestamps, and a version for conflict detection. Readable codes are separate, remain stable after creation, and are unique within their relevant scope. Engagement codes are globally unique; control, test, finding, evidence and action codes are unique per engagement. Codes are generated transactionally, never from the current row count. Do not reuse deleted codes.

| Entity | Required structure beyond common fields |
| --- | --- |
| Engagement | code, title, client_or_unit, scope, objectives, period_start/end, owner, status, methodology, executive_summary, completed_at, archived_at |
| Control | engagement_id, code, title, description, owner, risks_addressed, framework_references, testing_procedure, retired_at/reason |
| Test | engagement_id, control_id, code, procedure_snapshot, tester, execution_date, sample_description, work_performed, status, result, conclusion, applicability_or_limitation_rationale, no_finding_rationale |
| EvidenceReference | engagement_id, code, title, description, type, source, source_system, collection_date, owner, review_status, reviewer, reviewed_on, review_note/rejection_reason |
| Finding | engagement_id, code, title, condition, criteria, cause, impact, severity/rationale, recommendation, owner, status, resolution_verifier/date/conclusion, withdrawal_reason |
| RemediationAction | engagement_id, finding_id, code, description, owner, due_date, status, blocked_reason, closure_verifier/date/conclusion |
| ProgressUpdate | engagement_id, action_id, author, text, recorded_at; append new corrections rather than silently replacing prior updates |
| Relationship tables | test_evidence, finding_controls, finding_tests, finding_evidence, action_evidence (support/closure purpose), finding_closure_evidence; unique pairs and real foreign keys |
| ActivityEvent | engagement_id, entity_type/id, operation, actor_label or authenticated actor ID, timestamp, changed field names, necessary before/after values, reason; avoid credentials or document contents |

Normalize fields further where useful, while keeping the UI simple. Owners and local reviewers can be plain text; do not pretend these labels prove identity. Internal identifiers must never be treated as authorization credentials.

Enforce relationships in the database and service layer. Use composite engagement/id constraints or an equivalent reliable pattern so children and join rows cannot reference another engagement. Enable SQLite foreign keys on every connection if SQLite is used. Unique constraints, non-null constraints, and transactions must complement request validation.

Validate enum values, text length limits, date formats and relationships on the server. Set and document limits (for example 200 characters for titles, 2,048 for URLs, and 20,000 for narrative fields). Trim required text and reject whitespace-only values. Do not accept future execution, collection, or verification dates as completed events. Allow future audit periods and remediation due dates. Verification cannot predate the execution/closure event it verifies where applicable.

Perform record mutations and their activity entries in the same transaction. Use optimistic concurrency checks to prevent two open tabs silently overwriting one another. Return actionable conflict messages and let the user reload or reconcile.

Deletion is not the default lifecycle tool. Allow confirmed deletion of unlinked draft records only; block deletes with dependents and show those dependencies. Preserve issued findings, completed tests, progress updates and their disposition using reopen/withdraw/retire actions. Do not cascade-delete audit work as a convenience.

User-entered facts include narratives, dates, owner labels, results and reviewer assertions. Calculated values include counts, readiness, overdue flags, latest results and progress summaries. Derive calculated values from current stored records rather than allowing contradictory manual edits.

### Activity-history guarantees

Record creations, substantive edits, links/unlinks, lifecycle changes, retirement/archive/reopen actions, review decisions, due-date changes, and permitted deletions. Retain readable record codes in deletion events. Do not expose ordinary UI editing/deletion of activity events.

This is an application activity history, **not a tamper-proof audit trail**. Someone with database/file access can change or delete it; restores can roll back history. Local actor labels are self-asserted. Do not claim cryptographic integrity, independent verification, nonrepudiation, immutable retention, or regulatory-grade logging. More robust logging is a future requirement for an appropriately designed hosted deployment.

## 6. Technical implementation and operations

### Repository-first implementation

Inspect first, reuse existing dependencies, and make small coherent changes. If the repository is empty or lacks an established application, use a straightforward server-rendered Django application with SQLite, Django migrations, Django templates, and modest CSS/JavaScript. This fallback provides forms, ORM constraints, migrations, escaping, CSRF protection and tests with little infrastructure. Pin compatible supported dependencies during implementation; verify their current documentation then. Avoid introducing a separate SPA, queue, object store, Docker requirement, or paid service for this workflow.

Organize business validation, lifecycle transitions, readiness and export serialization into reusable service functions; do not duplicate rules in templates. Provide friendly not-found and validation errors without leaking other engagements. Use transactions and database constraints for atomic changes. Choose an equivalent simple architecture if the actual repository dictates a different stack, and explain it in the README.

### Persistence and configuration

- Store all records in a real database on disk; browser state and in-memory arrays are not the system of record.
- Commit schema migrations; document fresh initialization and upgrade commands. Never run destructive schema resets at startup.
- Configure the database path, secret key, local timezone and allowed hosts explicitly with safe local defaults. Supply an example environment file with placeholders and ignore real environment files, databases, backups, logs and generated audit reports in Git.
- Keep application data in a predictable writable data directory, outside static/public directories. Persist it across restarts and code updates. A container, if already used, needs a durable volume.
- Seed only fictional data through an explicit repeat-safe command. Do not recreate seed data on startup or substitute it for empty-state behavior.
- Handle database and export failures with a useful message and retained input, not a false success notification.

### Deployment and authentication

The default MVP runs on the auditor's machine, bound to `127.0.0.1`, with one operator. Authentication may be omitted only in this mode, clearly stated in the README and application UI. Restrict allowed hosts and origins, use CSRF protection for mutations, and do not allow arbitrary cross-origin requests. Local-only does not mean encrypted or protected from other users/processes on the same machine. Store data under appropriately restricted OS permissions.

Document exact install, migration, run, test, seed, backup and restore commands matching the delivered stack. For the Django fallback, provide a virtual-environment/dependency-install sequence, `python manage.py migrate`, `python manage.py runserver 127.0.0.1:8000`, and the actual test and management commands implemented. State supported runtime versions and all necessary environment variables.

Do not expose an unauthenticated development server to a LAN or public host. Network deployment requires authentication, HTTPS, production configuration, secure sessions, authorization enforced server-side on every record and export, and operational backup ownership. If multi-user behavior already exists or is implemented, define engagement membership and roles, enforce them for reads/writes/exports, prevent identifier-based cross-engagement access, and test both authorized and denied requests. Do not advertise multi-user security based only on hidden UI controls.

The complete core workflow must work offline after dependency installation, without paid services, AI APIs, or external document access.

## 7. Reporting and exports

Use one engagement report data builder shared by preview and exporters. Read a consistent database snapshot so a concurrent edit cannot yield contradictory sections. Include the engagement code/title, client/unit, audit period, owner, lifecycle state, generated-at timestamp/timezone and readiness state. Reports are generated views, not immutable signed artifacts; disclose that regeneration reflects current records.

The report must contain:

1. **Executive summary:** auditor-entered text plus clearly labelled calculated counts by test result and finding severity, outstanding actions, overdue actions, and limitations.
2. **Scope and objectives:** exact stored scope, objectives, client/unit, audit period and owner.
3. **Methodology:** entered methodology, applicable testing procedures, sampling details and limitations. Do not manufacture a methodology from a template.
4. **Control testing summary:** controls, framework references, owners, test procedures, executions, samples, results, conclusions and evidence codes. Include retired controls distinctly and retain historical tests.
5. **Detailed findings:** all stored findings with codes, status, severity rationale, condition, criteria, cause, impact, recommendation, control/test links and supporting evidence codes. Mark drafts, withdrawn and resolved items explicitly.
6. **Remediation plan:** actions grouped by finding with owners, due dates, status, overdue flags, dated progress updates and closure verification/evidence.
7. **Evidence-reference appendix:** every registered reference with code, type, title, description, source location/identifier, source system, collection date, owner, review state and usage links. Repeat the reference-only disclaimer.

Use explicit “Not provided”, “Not tested”, or “No records” labels as appropriate. Do not replace absence with “None identified” or a favorable conclusion. Include a readiness/limitations section listing unresolved blockers and warnings. All exports use stored records, with no fabricated content or hardcoded demo summaries.

### Required formats

- **Markdown:** one UTF-8 `.md` report, readable without the application. Escape user content so it cannot introduce unexpected raw HTML or malformed report structure. Preserve narrative line breaks and source strings safely.
- **CSV:** download a ZIP of UTF-8 CSV tables for engagement, controls, tests, evidence references, findings, remediation, progress updates and relationship rows. Include stable IDs, readable codes, engagement ID/code, predictable headers, ISO dates and export metadata. Include a small data dictionary; provide headers even for empty tables. Use a standard CSV serializer for quoting, commas, embedded quotes and newlines. Neutralize spreadsheet formula injection for user-entered fields beginning with dangerous formula prefixes, including after leading whitespace/control characters; document the protective prefix so it is not mistaken for source content. Preserve original values in the database.
- **Print-ready HTML:** show the same report data with print styles, hidden navigation/actions, sensible margins, repeating table headers where supported, wrapping long paths, and no clipped content. Provide a Print / Save as PDF action using browser printing. Explain that browser pagination can vary; a server-side PDF engine is not required.

Use safe filenames based on sanitized engagement code and generation date. Exports contain potentially sensitive metadata: generate downloads on request, do not publish them as public static files, and remind the operator to store them appropriately. Keep full original reference strings available in reports as escaped plain text even when a URL is unsafe to open.

## 8. Security, data handling, backup and recovery

- Validate server-side and render all user narratives as escaped text. If Markdown rendering is introduced, sanitize generated HTML; never execute raw HTML or scripts from audit content.
- Permit clickable evidence URLs only for validated `https` and `http` schemes. Show the destination before opening, use `noopener noreferrer` for new tabs, and reject executable schemes such as `javascript:` or `data:`. Render document paths and external IDs as copyable text, never shell commands or local-file launch actions.
- Do not fetch evidence URLs on the server, check arbitrary network locations, preview documents, read paths, or follow references automatically. This MVP avoids document ingestion and SSRF exposure from link fetching.
- Keep credentials, tokens, real evidence, database files, generated reports and backups out of source control. Do not log form payloads or evidence locations unnecessarily. Use fictional names, paths and URLs in tests/demos.
- Confirm retirement, withdrawal, archive, reopening, deletion and completion with the affected record and required reason where specified. Use POST or equivalent protected mutation requests, not state-changing GET links.
- Display sensitive local data only through the application; do not serve the database directory. Document that MVP storage and exports are not encrypted by the application.
- Provide a practical backup command using SQLite's supported backup API or an equivalent transaction-consistent database dump. Do not copy a live SQLite main file alone while WAL data may be outstanding. Record schema/app version and backup timestamp in a companion manifest.
- Document a suggested backup before upgrades and at the end of active work, stored on an access-controlled separate device/location. The operator chooses retention and encryption appropriate to the engagement.
- Restore with the app stopped into a new/test data path first; preserve the current database, verify database integrity and foreign keys, apply compatible migrations if required, then check engagement counts, relationships and report generation before switching paths. Include an actual backup/restore smoke test. A backup is not proven usable until a restore has been verified.

## 9. Build milestones and acceptance criteria

Implement in small verifiable increments, keeping the application runnable. Do not defer persistence or export integration until after building a cosmetic interface.

### Milestone 1 — repository assessment and persistent foundation

Inspect instructions/code and document the actual stack decision. Establish configuration, migrations, schema constraints, local startup and engagement creation/list/detail editing.

**Accept:** A fresh checkout can be initialized with documented commands; an empty database has useful empty states; saved engagement data survives a process restart; invalid dates and duplicate codes fail clearly; no demo seeding happens implicitly.

### Milestone 2 — controls, tests and references

Implement control CRUD/retirement, test procedures/results, evidence registration/review and relationships. Add activity recording and shared validation.

**Accept:** Tests retain procedure snapshots; invalid completed tests are rejected; evidence review requirements work; cross-engagement IDs cannot be linked even through direct requests; linked-reference deletion is blocked; edits/history commit atomically.

### Milestone 3 — findings and remediation

Implement finding narratives, severity, lifecycle, actions, progress updates, overdue badges and closure verification.

**Accept:** Opening incomplete findings fails; overdue uses the configured date boundary; due today is not overdue; completed action/finding rules are enforced server-side; invalid transition shortcuts fail; reopening preserves history and requires reasons.

### Milestone 4 — readiness and functional exports

Implement shared readiness checks, engagement lifecycle, report preview, Markdown, CSV ZIP and print stylesheet.

**Accept:** Draft reports visibly identify omissions; complete reports contain actual stored narratives and relationships; outstanding remediation is visible; register filters do not narrow reports; CSVs parse with stable headers and correct quoting; formula-like input is safe; long content prints without clipping; completed/archived work cannot be silently edited.

### Milestone 5 — verification, usability and handover

Finish focused tests, backup/restore verification, keyboard and print checks, startup documentation and known limitations. Fix relevant failures before declaring completion.

**Accept:** The scenario below passes against a real persistent database; relevant automated checks pass; restore succeeds into an independent data location; another operator can follow the README without guessing commands or secrets.

### Central end-to-end acceptance scenario

1. Start from an empty database. Create fictional engagement `DEMO-2026`, with client/unit, owner, scope, objectives and valid audit period; activate it.
2. Add at least two controls with risks, owners, framework references and testing procedures.
3. Register a URL reference, a document path, and an external document ID with source system, dates and owners. Review appropriate references and link them to tests.
4. Complete one effective test and one ineffective test with sample details, work performed, conclusions and reviewed support.
5. Raise an open high-severity finding linked to the ineffective test/control. Fill condition, criteria, cause, impact, recommendation and severity rationale; link reviewed evidence.
6. Assign an action with owner and a past due date; add a progress update. Verify that it appears overdue and the finding remains open.
7. Stop the application and start it again using the same configured database. Verify every created record, link, narrative, status and progress update remains, and no duplicate seed records appear.
8. Enter summary and methodology; inspect readiness, enter review and complete the engagement with the outstanding action disclosed. Download Markdown and CSVs and open the print view. Verify actual stored text, result counts, evidence source strings and overdue remediation are present.
9. Confirm that an edit to the completed engagement is rejected. Reopen with a reason, register/review closure evidence, complete the action with verification, then resolve the finding with a conclusion and verifier. Regenerate the report and verify the new disposition and retained history.
10. Create a second engagement and attempt cross-engagement linking by crafted request as well as through the UI; both must fail. Back up the database, restore to an independent path and verify the records and report there.

### Meaningful automated and manual checks

- Model/service tests for required fields, uniqueness, date boundaries, status transition matrix and closure requirements, including rejected transitions with no partial writes.
- Integration tests for real database persistence, foreign keys, cross-engagement relationships, restricted deletion, stale version conflicts and activity transaction rollback.
- Tests that substantively changing required evidence demands reopening dependents and resets review correctly.
- Export tests against known stored fixtures: complete and incomplete reports, no missing records, deterministic ordering/counts, Unicode, multiline text, quotes/commas, unsafe URLs, HTML payloads, formula-like CSV cells and empty tables.
- An end-to-end browser or equivalent integration test for the central journey, with a real database and an actual process restart or independently restarted server fixture. Do not assert restart persistence against a mocked in-memory store.
- Manual keyboard/form-error checks and print preview with multi-page findings and long reference strings. If browser automation is unavailable, document precisely what was manually verified and what remains unverified.
- Run existing repository checks plus relevant lint/type/build/test commands for the actual stack. Do not add tests merely to mirror implementation details, nor claim checks passed without running them.

## 10. Instructions to the implementing Codex agent

Implement the working application described here. Inspect the local repository and instructions first, preserve useful work, then complete the milestones. Make reasonable reversible decisions autonomously and record them briefly. Ask questions only when missing information materially blocks progress or an irreversible action needs authorization. Missing branding, optional integrations or a hosted deployment choice must not block the local MVP.

Run relevant checks, fix failures, and verify the full workflow. Document installation, configuration, migrations, startup, seed data, tests, backup/recovery and limitations in the repository README. Report what was implemented, which checks actually passed, and any material remaining gaps without unsupported assurance claims.

**Do not stop at a plan, static mockup, disconnected forms, or an interface backed only by temporary sample data. Completion requires a working application with persistent records, enforced relationships and lifecycle rules, and functional exports.** No deployment, paid service, external integration, or AI API is necessary for completion.

## Definition of done

- [ ] Repository instructions inspected; existing useful work preserved; stack decision documented.
- [ ] The complete engagement-to-report workflow works with real persistent records.
- [ ] Relationships, engagement isolation, lifecycle validation and closure rules are enforced server-side.
- [ ] Evidence is explicitly reference-only; safe links and review limitations are clear.
- [ ] Readiness, search, filters, empty states, cross-links and accessible forms are usable.
- [ ] Markdown, CSV and print-ready reports reflect stored records and expose incomplete information.
- [ ] Activity history is functional and its integrity limitations are accurately documented.
- [ ] Restart persistence and backup/restore are verified; relevant tests/checks pass.
- [ ] Setup, local-only authentication assumptions, commands and known limitations are documented.
- [ ] No credentials, real sensitive evidence or unsupported regulatory-compliance claims are included.

> Read `AUDIT_LEDGER_BUILD.md`, inspect this repository and its instructions, and implement Audit Ledger according to the brief. Complete the core workflow, verify it, and document how to run it.
