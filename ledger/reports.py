import csv
import html
import io
import json
import re
import zipfile
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Engagement, MODELS, Test, ProgressUpdate
from .schema import RELATIONS, LABELS
from .services import readiness, snapshot, primitive, evidence_usage

REFERENCE_NOTICE = 'References only: this application does not upload, store, fetch, verify or preserve the underlying documents. Review is an auditor assertion, not proof of accessibility, authenticity, completeness or integrity.'
HISTORY_NOTICE = 'Application activity history is editable by anyone with database/file access and may roll back on restore. Local actor labels are self-asserted; this is not a tamper-proof audit trail.'
REPORT_NOTICE = 'Generated view of current records, not an immutable or signed artifact. Regeneration reflects subsequent changes. Framework references do not establish compliance or assurance.'


def display(value):
    if value is None or value == '':
        return 'Not provided'
    return str(value)


@transaction.atomic
def build_report(engagement_id):
    e = Engagement.objects.get(pk=engagement_id)
    ready = readiness(e)
    generated = timezone.localtime()
    bundle = {'engagement': e, 'readiness': ready, 'generated_at': generated.isoformat(),
              'timezone': settings.TIME_ZONE, 'sections': [], 'tables': {},
              'draft': e.status != 'completed' or bool(ready['blockers']),
              'reference_notice': REFERENCE_NOTICE, 'history_notice': HISTORY_NOTICE, 'report_notice': REPORT_NOTICE}
    all_records = {}
    relation_codes = {}
    for kind in ['engagement', 'control', 'test', 'finding', 'action', 'evidence']:
        model = MODELS[kind]
        records = [e] if kind == 'engagement' else list(model.objects.filter(engagement=e).order_by(*(['finding__code', 'code', 'id'] if kind == 'action' else ['code', 'id'])))
        all_records[kind] = records
        for obj in records:
            relation_codes[str(obj.pk)] = obj.code
    base = {'exported_at': generated.isoformat(), 'app_version': settings.APP_VERSION,
            'export_timezone': settings.TIME_ZONE, 'engagement_id': str(e.pk), 'engagement_code': e.code}
    for kind, records in all_records.items():
        headers = list(base) + [f.name for f in MODELS[kind]._meta.fields if f.name not in base]
        rows = []
        titles = {'engagement': 'Engagement', 'control': 'Control testing summary', 'test': 'Test executions', 'finding': 'Detailed findings', 'action': 'Remediation plan · grouped by finding', 'evidence': 'Evidence-reference appendix'}
        section = {'title': titles[kind], 'kind': kind, 'records': []}
        for obj in records:
            raw = {f.name: primitive(getattr(obj, f.attname)) for f in obj._meta.fields}
            rows.append(base | raw)
            fields = []
            for name, value in raw.items():
                if name in ('id', 'engagement', 'version', 'created_at', 'updated_at', 'code'):
                    continue
                field = obj._meta.get_field(name)
                if field.choices:
                    value = dict(field.choices).get(value, value)
                if field.is_relation:
                    value = relation_codes.get(str(value), value)
                fields.append({'label': str(field.verbose_name).replace('_', ' ').capitalize(), 'value': display(value)})
            for name in RELATIONS.get(kind, {}):
                codes = [r.code for r in getattr(obj, name).all()]
                fields.append({'label': name.replace('_', ' ').capitalize(), 'value': ', '.join(codes) or 'No records'})
            if kind == 'control':
                fields += [{'label': 'Disposition', 'value': 'Retired' if obj.retired_at else 'Active'},
                           {'label': 'Latest completed result (not an overall opinion)', 'value': obj.latest_result}]
            if kind == 'evidence':
                fields.append({'label': 'Used by', 'value': ', '.join(r.code for r in evidence_usage(obj)) or 'Unused reference'})
            progress = []
            if kind == 'action':
                fields.append({'label': 'Overdue', 'value': 'Yes' if obj.overdue else 'No'})
                progress = [{'author': p.author, 'text': p.text, 'recorded_at': timezone.localtime(p.recorded_at).isoformat()} for p in obj.progress_updates.all()]
            section['records'].append({'code': obj.code, 'title': getattr(obj, 'title', getattr(obj, 'description', '')),
                                       'url': obj.get_absolute_url(), 'fields': fields, 'progress': progress,
                                       'has_progress': kind == 'action'})
        bundle['tables'][kind] = {'headers': headers, 'rows': rows}
        if kind != 'engagement':
            bundle['sections'].append(section)
    progress_headers = list(base) + ['id', 'action', 'action_code', 'author', 'text', 'recorded_at']
    bundle['tables']['progress_updates'] = {'headers': progress_headers, 'rows': [base | {
        'id': str(p.pk), 'action': str(p.action_id), 'action_code': p.action.code,
        'author': p.author, 'text': p.text, 'recorded_at': p.recorded_at.isoformat(),
    } for p in ProgressUpdate.objects.filter(engagement=e).select_related('action')]}
    for kind, mappings in RELATIONS.items():
        for name, (_model, through, origin, target) in mappings.items():
            table = f'{kind}_{name}'
            headers = list(base) + ['id', f'{origin}_id', f'{origin}_code', f'{target}_id', f'{target}_code']
            rows = []
            for link in through.objects.filter(engagement=e).order_by('id'):
                left, right = str(getattr(link, f'{origin}_id')), str(getattr(link, f'{target}_id'))
                rows.append(base | {'id': link.pk, f'{origin}_id': left, f'{origin}_code': relation_codes[left],
                                    f'{target}_id': right, f'{target}_code': relation_codes[right]})
            bundle['tables'][table] = {'headers': headers, 'rows': rows}
    # Include readable prior closure details and disposition history in every format.
    history_rows = []
    for event in e.activityevent_set.all().order_by('timestamp', 'id'):
        history_rows.append(base | {'id': str(event.pk), 'entity_type': event.entity_type,
                                    'entity_id': str(event.entity_id), 'entity_code': event.entity_code,
                                    'operation': event.operation, 'actor_label': event.actor_label,
                                    'timestamp': event.timestamp.isoformat(), 'reason': event.reason,
                                    'changes': json.dumps(event.changes, ensure_ascii=False, sort_keys=True)})
    bundle['tables']['history'] = {'headers': list(base) + ['id', 'entity_type', 'entity_id', 'entity_code', 'operation', 'actor_label', 'timestamp', 'reason', 'changes'], 'rows': history_rows}
    bundle['history'] = history_rows
    return bundle


def safe_filename(bundle, extension):
    code = re.sub(r'[^A-Za-z0-9_-]+', '-', bundle['engagement'].code).strip('-')[:60] or 'engagement'
    return f'{code}-{bundle["generated_at"][:10]}.{extension}'


def markdown_text(value):
    # Escape raw HTML and all Markdown structural punctuation in untrusted text.
    value = html.escape(display(value), quote=False)
    value = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', value)
    return '  \n'.join(value.splitlines())


def markdown_report(bundle):
    e = bundle['engagement']
    ready = bundle['readiness']
    lines = [f'# Audit Ledger — {markdown_text(e.code)}', '', markdown_text(e.title), '',
             '**DRAFT / INCOMPLETE**' if bundle['draft'] else '**COMPLETED ENGAGEMENT**', '',
             f'Generated: {markdown_text(bundle["generated_at"])} ({markdown_text(bundle["timezone"])})', '',
             REPORT_NOTICE, '', '## Readiness and limitations', '']
    for issue in ready['blockers']:
        lines.append(f'- BLOCKER · {markdown_text(issue["code"])}: {markdown_text(issue["message"])}')
    for issue in ready['warnings']:
        lines.append(f'- WARNING · {markdown_text(issue["code"])}: {markdown_text(issue["message"])}')
    if not ready['blockers'] and not ready['warnings']:
        lines.append('No readiness blockers or warnings under the application rules. This does not infer assurance.')
    lines += ['', '## Executive summary', '', markdown_text(e.executive_summary), '', '### Calculated counts', '']
    for key, value in ready['counts'].items():
        if isinstance(value, dict):
            for label, count in value.items():
                lines.append(f'- {key.replace("_", " ")} / {label.replace("_", " ")}: {count}')
        else:
            lines.append(f'- {key.replace("_", " ")}: {value}')
    lines += ['', '## Scope and objectives', '']
    for label, value in [('Client / unit', e.client_or_unit), ('Owner', e.owner), ('Audit period', f'{e.period_start} – {e.period_end}'),
                         ('Status', e.get_status_display()), ('Completed at', e.completed_at), ('Archived at', e.archived_at),
                         ('Scope', e.scope), ('Objectives', e.objectives), ('Methodology', e.methodology)]:
        lines += [f'### {label}', '', markdown_text(value), '']
    for section in bundle['sections']:
        lines += [f'## {section["title"]}', '']
        if section['kind'] == 'evidence':
            lines += [REFERENCE_NOTICE, '']
        if not section['records']:
            lines += ['No records', '']
        for record in section['records']:
            lines += [f'### {markdown_text(record["code"])}', '']
            for field in record['fields']:
                lines += [f'**{field["label"]}**', '', markdown_text(field['value']), '']
            for p in record['progress']:
                lines += [f'**Progress · {markdown_text(p["recorded_at"])} · {markdown_text(p["author"])}**', '', markdown_text(p['text']), '']
    lines += ['## Activity history', '', HISTORY_NOTICE, '']
    for event in bundle['history']:
        lines += [f'### {markdown_text(event["entity_code"])} · {markdown_text(event["operation"])}', '',
                  markdown_text(f'{event["timestamp"]} · {event["actor_label"]}'), '', markdown_text(event['reason']), '',
                  markdown_text(event['changes']), '']
    return '\n'.join(lines)


def csv_safe(value):
    if value is None:
        return ''
    value = str(value)
    probe = value
    while probe and (probe[0].isspace() or ord(probe[0]) <= 32 or probe[0] == '\ufeff'):
        probe = probe[1:]
    if probe.startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def csv_bundle(bundle):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, table in bundle['tables'].items():
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=table['headers'])
            writer.writeheader()
            for row in table['rows']:
                writer.writerow({k: csv_safe(v) for k, v in row.items() if k in table['headers']})
            archive.writestr(name + '.csv', stream.getvalue().encode('utf-8-sig'))
        dictionary = ['Audit Ledger CSV data dictionary',
                      f'App version: {settings.APP_VERSION}. Generated: {bundle["generated_at"]}. Timezone: {bundle["timezone"]}.',
                      'UTF-8 with BOM; ISO dates; UTC persisted timestamps; UUID stable record IDs. Empty cell = not provided.',
                      'All tables include engagement ID/code and export metadata. Parent and relationship IDs join to entity IDs.',
                      'Readable codes are stable, unique per engagement (engagement codes globally unique). Version supports optimistic concurrency.',
                      'Formula safety: a leading apostrophe is added to cells with formula prefixes (=,+,-,@), including after whitespace/control characters, and leading tabs/newlines. This protective prefix is NOT part of the original database value.',
                      'action_evidence is supporting evidence; action_closure_evidence is verification evidence. Finding closure is distinct from finding support.',
                      'History changes are JSON maps of changed field names to before/after values. Prior verification details remain here after reopening.',
                      'Counts, readiness and overdue are calculated; due today is not overdue. Latest test result is not an overall opinion.',
                      REFERENCE_NOTICE, HISTORY_NOTICE, REPORT_NOTICE,
                      'These files contain potentially sensitive metadata. Store with appropriate access controls. Storage is not encrypted by this application.', '']
        for name, table in bundle['tables'].items():
            dictionary.append(name + '.csv: ' + ', '.join(table['headers']))
        archive.writestr('DATA_DICTIONARY.txt', '\n'.join(dictionary))
        archive.writestr('report.md', markdown_report(bundle))
    return output.getvalue()
