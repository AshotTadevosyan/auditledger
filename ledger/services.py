"""All application mutations, domain rules and report readiness.

Mutations use SQLite IMMEDIATE transactions, compare record versions, write
relationships and append history atomically. No view calls Model.save().
"""
import datetime
import uuid
from collections import Counter
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from .models import (MODELS, PREFIXES, Engagement, Control, Test, Evidence, Finding,
                     Action, ActivityEvent, ProgressUpdate, CodeSequence)
from .schema import FIELDS, RELATIONS


class Conflict(ValidationError):
    pass


def fail(message, field=None):
    raise ValidationError({field: message} if field else message)


def text_required(obj, names):
    return [f'{name.replace("_", " ").capitalize()} is required.' for name in names
            if not str(getattr(obj, name, '') or '').strip()]


def date_errors(value, label, earliest=None):
    if not value:
        return [f'{label} is required.']
    errors = []
    if value > timezone.localdate():
        errors.append(f'{label} cannot be in the future.')
    if earliest and value < earliest:
        errors.append(f'{label} cannot precede {earliest.isoformat()}.')
    return errors


def reviewed_errors(query, required=False, label='Supporting evidence'):
    records = list(query)
    errors = []
    if required and not records:
        errors.append(f'{label} requires at least one reviewed reference.')
    for reference in records:
        if reference.review_status != 'reviewed':
            errors.append(f'{label}: {reference.code} must be reviewed.')
    return errors


def entity_errors(obj, state=None):
    state = state or getattr(obj, 'status', '')
    errors = []
    if obj.kind == 'engagement':
        errors += text_required(obj, ['title', 'client_or_unit', 'owner'])
        if state != 'draft':
            errors += text_required(obj, ['scope', 'objectives'])
    elif obj.kind == 'control':
        errors += text_required(obj, ['title', 'description', 'owner', 'risks_addressed', 'testing_procedure'])
    elif obj.kind == 'evidence':
        errors += text_required(obj, ['title', 'description', 'source', 'owner'])
        if obj.type == 'external_document_id':
            errors += text_required(obj, ['source_system'])
        errors += date_errors(obj.collection_date, 'Collection date')
        if obj.review_status == 'reviewed':
            errors += text_required(obj, ['reviewer', 'review_note'])
            errors += date_errors(obj.reviewed_on, 'Review date', obj.collection_date)
        elif obj.review_status == 'rejected':
            errors += text_required(obj, ['rejection_reason'])
    elif obj.kind == 'test' and state == 'completed':
        errors += text_required(obj, ['tester', 'procedure_snapshot', 'sample_description', 'work_performed', 'result', 'conclusion'])
        errors += date_errors(obj.execution_date, 'Execution date')
        if obj.result in ('not_applicable', 'unable_to_conclude'):
            errors += text_required(obj, ['applicability_or_limitation_rationale'])
        errors += reviewed_errors(obj.evidence.all(), obj.result in ('effective', 'partially_effective', 'ineffective'))
    elif obj.kind == 'finding' and state in ('open', 'resolved'):
        errors += text_required(obj, ['title', 'condition', 'criteria', 'cause', 'impact', 'severity_rationale', 'recommendation', 'owner'])
        if not obj.controls.exists():
            errors.append('At least one related control is required.')
        errors += reviewed_errors(obj.evidence.all(), True)
        control_ids = {c.pk for c in obj.controls.all()}
        if any(t.control_id not in control_ids for t in obj.tests.all()):
            errors.append('Related tests must belong to the linked controls.')
        if state == 'resolved':
            actions = list(obj.actions.all())
            if not actions:
                errors.append('Resolution requires at least one completed action.')
            if any(a.status != 'completed' for a in actions):
                errors.append('Every remediation action must be completed before resolution.')
            errors += text_required(obj, ['resolution_verifier', 'resolution_conclusion'])
            dates = [a.closure_date for a in actions if a.closure_date]
            dates += [t.execution_date for t in obj.tests.all() if t.execution_date]
            dates += [r.collection_date for r in obj.closure_evidence.all()]
            errors += date_errors(obj.resolution_date, 'Resolution date', max(dates, default=None))
            errors += reviewed_errors(obj.closure_evidence.all(), True, 'Closure evidence')
    elif obj.kind == 'action':
        errors += text_required(obj, ['description', 'owner'])
        if not obj.due_date:
            errors.append('Due date is required.')
        if state == 'blocked':
            errors += text_required(obj, ['blocked_reason'])
        if state == 'completed':
            errors += text_required(obj, ['closure_verifier', 'closure_conclusion'])
            dates = [r.collection_date for r in obj.closure_evidence.all()]
            if obj.ready_at:
                dates.append(timezone.localdate(obj.ready_at))
            dates += [t.execution_date for t in obj.finding.tests.all() if t.execution_date]
            errors += date_errors(obj.closure_date, 'Verification date', max(dates, default=None))
            errors += reviewed_errors(obj.closure_evidence.all(), True, 'Closure evidence')
            errors += reviewed_errors(obj.evidence.all())
    return errors


def primitive(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def snapshot(obj):
    result = {f.name: primitive(getattr(obj, f.attname)) for f in obj._meta.fields
              if f.name not in ('updated_at', 'version')}
    for name in RELATIONS.get(obj.kind, {}):
        result[name] = sorted(str(pk) for pk in getattr(obj, name).values_list('pk', flat=True))
    return result


def activity(obj, before, operation, actor, reason='', extra_changes=None):
    actor = str(actor or '').strip()
    if not actor or len(actor) > 200:
        fail('An actor label of 1–200 characters is required.', 'actor')
    if len(reason) > 20000:
        fail('Reason cannot exceed 20,000 characters.', 'reason')
    after = {} if operation == 'delete' else snapshot(obj)
    changes = {k: {'before': before.get(k), 'after': after.get(k)}
               for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    changes.update(extra_changes or {})
    ActivityEvent.objects.create(
        engagement=obj if obj.kind == 'engagement' else obj.engagement,
        entity_type=obj.kind, entity_id=obj.pk, entity_code=obj.code,
        operation=operation, actor_label=actor, changes=changes, reason=reason,
    )


def editable(engagement):
    if engagement.archived_at:
        fail('This engagement is archived. Unarchive it before making changes.')
    if engagement.status == 'completed':
        fail('This engagement is completed and read-only. Reopen it with a reason first.')
    if engagement.status == 'in_review':
        fail('Return the engagement to active with a reason before changing audit work.')


def get_current(kind, pk, engagement_id, version):
    model = MODELS[kind]
    query = model.objects.filter(pk=pk)
    if kind != 'engagement':
        query = query.filter(engagement_id=engagement_id)
    obj = query.get()
    if str(obj.version) != str(version):
        raise Conflict('This record changed in another tab. Your input is retained. Open the current record in a new tab, reconcile your changes, then reload before saving.')
    return obj


def bump(obj):
    old = obj.version
    obj.version += 1
    obj.updated_at = timezone.now()
    values = {f.attname: getattr(obj, f.attname) for f in obj._meta.fields if not f.primary_key}
    if not obj.__class__.objects.filter(pk=obj.pk, version=old).update(**values):
        raise Conflict('This record changed in another tab. Reload and reconcile your changes.')


def generate_code(kind, engagement=None):
    scope = f'{engagement.pk if engagement else "global"}:{kind}'
    sequence, _ = CodeSequence.objects.get_or_create(scope=scope)
    while True:
        sequence.value += 1
        sequence.save(update_fields=['value'])
        code = f'{PREFIXES[kind]}-{sequence.value:04d}'
        query = MODELS[kind].objects.filter(code=code)
        if engagement:
            query = query.filter(engagement=engagement)
        if not query.exists():
            return code


def set_relationships(obj, relations):
    for name, values in relations.items():
        if name not in RELATIONS.get(obj.kind, {}):
            fail('Unknown relationship.')
        target, through, origin_key, target_key = RELATIONS[obj.kind][name]
        ids = {str(v.pk if hasattr(v, 'pk') else v) for v in values}
        rows = list(target.objects.filter(pk__in=ids, engagement_id=obj.engagement_id))
        if len(rows) != len(ids):
            fail('All related records must belong to this engagement.', name)
        existing = through.objects.filter(**{origin_key: obj})
        existing.exclude(**{f'{target_key}_id__in': ids}).delete()
        for row in rows:
            through.objects.get_or_create(engagement=obj.engagement, **{origin_key: obj, target_key: row})
    if obj.kind == 'finding':
        control_ids = {c.pk for c in obj.controls.all()}
        if any(t.control_id not in control_ids for t in obj.tests.all()):
            fail('Select the controls that own each related test.', 'tests')


def evidence_dependencies(obj):
    dependencies = list(obj.tests.filter(status='completed'))
    dependencies += list(obj.findings.filter(status__in=['open', 'resolved']))
    dependencies += list(obj.closed_findings.filter(status='resolved'))
    dependencies += list(obj.closed_actions.filter(status='completed'))
    dependencies += list(obj.actions.filter(status='completed'))
    return list({record.pk: record for record in dependencies}.values())


def evidence_usage(obj):
    records = []
    for accessor in ('tests', 'findings', 'closed_findings', 'actions', 'closed_actions'):
        records += list(getattr(obj, accessor).all())
    return list({record.pk: record for record in records}.values())


def protect_test(obj):
    findings = list(obj.findings.filter(status='resolved').order_by('code', 'id'))
    if findings:
        fail('Test ' + obj.code + ' supports resolved findings: ' + ', '.join(f.code for f in findings) +
             '. Reopen every listed finding first (and the engagement if completed). For follow-up testing, create a separate test to retain this execution.')


def check_parent(obj):
    if obj.kind == 'test' and obj.control.engagement_id != obj.engagement_id:
        fail('Control must belong to this engagement.', 'control')
    if obj.kind == 'action':
        if obj.finding.engagement_id != obj.engagement_id:
            fail('Finding must belong to this engagement.', 'finding')
        if obj.finding.status != 'open':
            fail('Remediation may only be changed for an open finding. Open or reopen the finding first.')


@transaction.atomic
def save_record(kind, data, actor, engagement_id=None, pk=None, version=None, relations=None, reason='', procedure_source=None):
    if kind not in MODELS:
        fail('Unknown record type.')
    relations = relations or {}
    creating = pk is None
    if creating:
        engagement = Engagement.objects.get(pk=engagement_id) if kind != 'engagement' else None
        if engagement:
            editable(engagement)
        obj = MODELS[kind]()
        if engagement:
            obj.engagement = engagement
        before = {}
        obj.code = str(data.get('code') or generate_code(kind, engagement)).strip()
    else:
        obj = get_current(kind, pk, engagement_id, version)
        engagement = obj if kind == 'engagement' else Engagement.objects.get(pk=obj.engagement_id)
        editable(engagement)
        if kind == 'test':
            protect_test(obj)
        if ((kind in ('test', 'action') and obj.status == 'completed') or
                (kind == 'finding' and obj.status in ('resolved', 'withdrawn'))):
            fail('Reopen this record with a reason before editing it.')
        before = snapshot(obj)
    unknown = set(data) - set(FIELDS[kind]) - {'code'}
    if unknown:
        fail('These fields cannot be changed here: ' + ', '.join(sorted(unknown)))
    if not creating and 'code' in data and str(data['code']) != obj.code:
        fail('Readable codes are stable and cannot be changed.', 'code')
    for field in FIELDS[kind]:
        if field in data:
            value = data[field]
            setattr(obj, field, value.strip() if isinstance(value, str) else value)
    check_parent(obj)
    if kind == 'test' and creating and procedure_source:
        source_id, source_version, reconciled = procedure_source
        current_control = Control.objects.get(pk=obj.control_id, engagement_id=engagement.pk)
        if not reconciled and (str(current_control.pk) != str(source_id) or str(current_control.version) != str(source_version)):
            raise Conflict('The source control or its version changed. Compare the selected control’s current procedure in a new tab, reconcile your retained procedure, then explicitly confirm reconciliation.')
    if kind == 'test' and creating and not obj.procedure_snapshot:
        # Caller may hold an old model instance. Snapshot the stored procedure
        # inside the write transaction, not that caller's cached object.
        obj.control = Control.objects.get(pk=obj.control_id, engagement_id=engagement.pk)
        obj.procedure_snapshot = obj.control.testing_procedure
    if kind in ('test', 'action') and not creating:
        field = 'control' if kind == 'test' else 'finding'
        if str(getattr(obj, f'{field}_id')) != before[field]:
            fail(f'The parent {field} cannot be changed after creation.', field)
    if kind == 'action' and not creating and primitive(obj.due_date) != before['due_date'] and not reason.strip():
        fail('Explain why the due date is changing.', 'reason')
    if kind == 'evidence' and not creating:
        substantive = any(primitive(getattr(obj, name)) != before[name] for name in
                          ('source', 'type', 'source_system', 'description', 'collection_date', 'owner', 'notes'))
        if substantive:
            dependencies = evidence_dependencies(obj)
            if dependencies:
                fail('Reference is required by ' + ', '.join(r.code for r in dependencies) +
                     '. Reopen completed dependents; replace/unlink open-finding support before changing this reference.')
            obj.review_status = 'unreviewed'
            obj.reviewer = obj.review_note = obj.rejection_reason = ''
            obj.reviewed_on = None
    check_parent(obj)
    obj.full_clean(exclude=[])
    if kind == 'test' and obj.execution_date:
        errors = date_errors(obj.execution_date, 'Execution date')
        if errors:
            raise ValidationError(errors)
    if kind == 'evidence':
        errors = entity_errors(obj)
        if obj.type == 'url' and not obj.safe_url:
            errors.append('URL references require a complete http:// or https:// destination without credentials or control characters.')
        if errors:
            raise ValidationError(errors)
    if creating:
        obj.save(force_insert=True)
    set_relationships(obj, relations)
    if kind in ('action', 'finding', 'engagement'):
        errors = entity_errors(obj)
        if errors:
            raise ValidationError(errors)
    if not creating:
        bump(obj)
    activity(obj, before, 'create' if creating else 'edit', actor, reason)
    return obj


TRANSITIONS = {
    'engagement': {'draft': ['active'], 'active': ['in_review'], 'in_review': ['active', 'completed'], 'completed': ['active']},
    'test': {'planned': ['in_progress', 'completed'], 'in_progress': ['completed'], 'completed': ['in_progress']},
    'finding': {'draft': ['open', 'withdrawn'], 'open': ['resolved', 'withdrawn'], 'resolved': ['open'], 'withdrawn': ['open']},
    'action': {'not_started': ['in_progress', 'ready_for_verification', 'blocked'], 'in_progress': ['ready_for_verification', 'blocked'],
               'blocked': ['in_progress'], 'ready_for_verification': ['completed', 'in_progress'], 'completed': ['in_progress']},
    'evidence': {'unreviewed': ['reviewed', 'rejected'], 'reviewed': ['unreviewed'], 'rejected': ['unreviewed']},
}


@transaction.atomic
def transition(kind, pk, engagement_id, version, target, actor, reason='', details=None, confirmed=False):
    obj = get_current(kind, pk, engagement_id, version)
    engagement = obj if kind == 'engagement' else Engagement.objects.get(pk=obj.engagement_id)
    if not confirmed:
        fail(f'Confirm the change to {obj.code}.')
    before = snapshot(obj)
    details = details or {}
    if target == 'unarchive' and kind == 'engagement':
        if not obj.archived_at:
            fail('This engagement is not archived.')
        obj.archived_at = None
    elif target == 'archive' and kind == 'engagement':
        if obj.archived_at or obj.status not in ('draft', 'completed'):
            fail('Only draft or completed engagements may be archived.')
        obj.archived_at = timezone.now()
    elif kind == 'control' and target in ('retire', 'restore'):
        editable(engagement)
        if not reason.strip():
            fail('A reason is required.', 'reason')
        if bool(obj.retired_at) == (target == 'retire'):
            fail('This control is already in that state.')
        obj.retired_at = timezone.now() if target == 'retire' else None
        obj.retirement_reason = reason
    else:
        if kind != 'engagement':
            editable(engagement)
        elif obj.archived_at:
            fail('Unarchive the engagement before changing its lifecycle.')
        state_field = 'review_status' if kind == 'evidence' else 'status'
        previous = getattr(obj, state_field)
        if target not in TRANSITIONS.get(kind, {}).get(previous, []):
            fail(f'Cannot move {obj.code} from {previous.replace("_", " ")} to {target.replace("_", " ")}.')
        requires_reason = (previous in ('completed', 'resolved', 'withdrawn', 'rejected', 'reviewed', 'blocked') or
                           target in ('withdrawn', 'blocked') or
                           (previous == 'in_review' and target == 'active') or
                           (previous == 'ready_for_verification' and target == 'in_progress'))
        if requires_reason and not reason.strip():
            fail('A reason is required for this transition.', 'reason')
        if kind == 'test':
            protect_test(obj)
        if kind == 'action':
            check_parent(obj)
            if target == 'blocked':
                obj.blocked_reason = reason
            if target == 'ready_for_verification':
                obj.ready_at = timezone.now()
        if kind == 'finding' and target == 'withdrawn':
            obj.withdrawal_reason = reason
        if kind == 'evidence':
            if previous == 'reviewed' and evidence_dependencies(obj):
                fail('Reference is required by ' + ', '.join(r.code for r in evidence_dependencies(obj)) + '. Reopen completed dependents (including their parent findings); replace/unlink open-finding support before resetting this review.')
            if target == 'reviewed':
                for name in ('reviewer', 'reviewed_on', 'review_note'):
                    setattr(obj, name, details.get(name))
            if target == 'rejected':
                obj.rejection_reason = reason or details.get('rejection_reason', '')
            if target == 'unreviewed':
                obj.reviewer = obj.review_note = obj.rejection_reason = ''
                obj.reviewed_on = None
        setattr(obj, state_field, target)
        obj.full_clean()
        errors = entity_errors(obj, target)
        if kind == 'engagement':
            if target in ('in_review', 'completed'):
                ready = readiness(obj)
                errors += [x['message'] for x in ready['blockers'] if target == 'completed' or not x.get('completion_only')]
            if target == 'completed':
                obj.completed_at = timezone.now()
            elif previous == 'completed':
                obj.completed_at = None
        if errors:
            raise ValidationError(errors)
    bump(obj)
    activity(obj, before, target, actor, reason)
    return obj


@transaction.atomic
def add_progress(action_id, engagement_id, version, author, text):
    obj = get_current('action', action_id, engagement_id, version)
    editable(obj.engagement)
    check_parent(obj)
    if obj.status == 'completed':
        fail('Reopen the action before appending progress.')
    if not author.strip() or not text.strip():
        fail('Author and progress text are required.')
    update = ProgressUpdate(engagement=obj.engagement, action=obj, author=author.strip(), text=text.strip())
    update.full_clean()
    update.save()
    before = snapshot(obj)
    bump(obj)
    activity(obj, before, 'progress_update', author, extra_changes={
        'progress_update': {'before': None, 'after': {
            'id': str(update.pk), 'author': update.author, 'text': update.text,
            'recorded_at': update.recorded_at.isoformat(),
        }},
    })
    return update


def dependencies(obj):
    if obj.kind == 'control':
        return list(obj.test_set.all()) + list(obj.findings.all())
    if obj.kind == 'test':
        return list(obj.findings.all()) + list(obj.evidence.all())
    if obj.kind == 'evidence':
        return evidence_usage(obj)
    if obj.kind == 'finding':
        return list(obj.actions.all()) + list(obj.controls.all()) + list(obj.tests.all()) + list(obj.evidence.all()) + list(obj.closure_evidence.all())
    if obj.kind == 'action':
        return list(obj.evidence.all()) + list(obj.closure_evidence.all()) + list(obj.progress_updates.all())
    return []


@transaction.atomic
def delete_record(kind, pk, engagement_id, version, actor, confirmed=False):
    obj = get_current(kind, pk, engagement_id, version)
    editable(obj.engagement if kind != 'engagement' else obj)
    if not confirmed:
        fail('Explicit confirmation is required.')
    if kind == 'engagement' or (kind == 'test' and obj.status != 'planned') or (kind == 'finding' and obj.status != 'draft') or (kind == 'action' and obj.status != 'not_started') or (kind == 'evidence' and obj.review_status != 'unreviewed') or (kind == 'control' and obj.retired_at):
        fail('Only unlinked draft records may be deleted. Use the lifecycle actions to retain issued work.')
    linked = dependencies(obj)
    if linked:
        fail('Deletion blocked by linked records: ' + ', '.join(getattr(r, 'code', 'progress update') for r in linked) + '. Unlink editable records or reopen completed records first.')
    activity(obj, snapshot(obj), 'delete', actor)
    obj.delete()


def engagement_records(engagement):
    """One bounded set of relationship queries, reused by readiness and exports."""
    paths = {
        'control': ['test_set'],
        'test': ['evidence', 'findings'],
        'finding': ['controls', 'tests', 'evidence', 'closure_evidence', 'actions'],
        'action': ['evidence', 'closure_evidence', 'finding__tests', 'progress_updates'],
        'evidence': ['tests', 'findings', 'closed_findings', 'actions', 'closed_actions'],
    }
    return {kind: list(MODELS[kind].objects.filter(engagement=engagement)
                      .prefetch_related(*relations).order_by('code', 'id'))
            for kind, relations in paths.items()}


def readiness(engagement, records=None):
    blockers, warnings = [], []
    def item(target, message, completion_only=False):
        return {'message': message, 'url': target.get_absolute_url(), 'code': target.code, 'completion_only': completion_only}
    for error in entity_errors(engagement, 'active'):
        blockers.append(item(engagement, error))
    for name in ('methodology', 'executive_summary'):
        if not getattr(engagement, name).strip():
            blockers.append(item(engagement, name.replace('_', ' ').capitalize() + ' is required for completion.', True))
    records = records or engagement_records(engagement)
    controls, tests, findings, actions, evidence = (records[k] for k in ('control', 'test', 'finding', 'action', 'evidence'))
    if not any(not c.retired_at for c in controls):
        blockers.append(item(engagement, 'Add at least one active control.'))
    for control in controls:
        if control.retired_at:
            continue
        for error in entity_errors(control):
            blockers.append(item(control, error))
        if not any(t.control_id == control.pk and t.status == 'completed' for t in tests):
            blockers.append(item(control, 'Active control needs a completed test.'))
    for test in tests:
        if test.status != 'completed':
            blockers.append(item(test, 'Test is still ' + test.get_status_display().lower() + '.'))
        else:
            for error in entity_errors(test):
                blockers.append(item(test, error))
            if test.result in ('ineffective', 'partially_effective') and not test.no_finding_rationale.strip() and not any(f.status in ('open', 'resolved') for f in test.findings.all()):
                blockers.append(item(test, 'Link an open/resolved finding or document why no finding was raised.'))
            if test.result == 'unable_to_conclude':
                warnings.append(item(test, 'Unable to conclude: ' + test.applicability_or_limitation_rationale))
    for finding in findings:
        if finding.status == 'draft':
            blockers.append(item(finding, 'Draft finding must be completed and opened, or withdrawn with a reason.'))
        for error in entity_errors(finding):
            blockers.append(item(finding, error))
        if finding.status == 'open' and not finding.actions.exists():
            blockers.append(item(finding, 'Open finding needs a remediation action with owner and due date.'))
    for action in actions:
        for error in entity_errors(action):
            blockers.append(item(action, error))
        if action.status != 'completed':
            warnings.append(item(action, 'Outstanding remediation: ' + action.description))
        if action.overdue:
            warnings.append(item(action, f'Overdue since {action.due_date.isoformat()}; owner: {action.owner}.'))
    for reference in evidence:
        for error in entity_errors(reference):
            blockers.append(item(reference, error))
        if not evidence_usage(reference):
            warnings.append(item(reference, 'Unused evidence reference (informational).'))
    counts = {'controls': len(controls), 'active_controls': sum(not c.retired_at for c in controls),
              'tests': len(tests), 'completed_tests': sum(t.status == 'completed' for t in tests),
              'findings': len(findings), 'open_findings': sum(f.status == 'open' for f in findings),
              'evidence': len(evidence), 'actions': len(actions),
              'outstanding': sum(a.status != 'completed' for a in actions), 'overdue': sum(a.overdue for a in actions),
              'test_results': {key: sum(t.status == 'completed' and t.result == key for t in tests) for key, _ in Test.RESULTS},
              'severities': {key: sum(f.severity == key for f in findings) for key, _ in Finding.SEVERITY}}
    return {'blockers': blockers, 'warnings': warnings, 'counts': counts,
            'review_ready': not any(not x['completion_only'] for x in blockers), 'completion_ready': not blockers}
