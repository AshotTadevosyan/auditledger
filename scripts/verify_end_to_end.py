#!/usr/bin/env python3
"""Real HTTP/CSRF workflow, process restart, and independent backup/restore.

Uses temporary databases only. No browser automation package or mock store.
Run from repo root: .venv/bin/python scripts/verify_end_to_end.py
"""
import csv
import hashlib
import html
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

if '--fingerprint' in sys.argv:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.apps import apps
    from django.core.serializers.json import DjangoJSONEncoder
    snapshot = {}
    for model in apps.get_app_config('ledger').get_models():
        snapshot[model.__name__] = list(model.objects.order_by('pk').values())
    encoded = json.dumps(snapshot, cls=DjangoJSONEncoder, sort_keys=True).encode()
    print(hashlib.sha256(encoded).hexdigest())
    raise SystemExit(0)


def main():
    with tempfile.TemporaryDirectory(prefix='audit-ledger-e2e-') as temporary:
        temp = Path(temporary)
        env = os.environ | {'AUDIT_DB_PATH': str(temp / 'working.sqlite3'), 'AUDIT_TIME_ZONE': 'Asia/Yerevan',
                            'AUDIT_ALLOWED_HOSTS': '127.0.0.1,localhost', 'PYTHONUNBUFFERED': '1'}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        cookies = http.cookiejar.CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookies))
        server = None
        log = (temp / 'server.log').open('w+')

        def command(*args, current_env=None):
            result = subprocess.run([PYTHON, 'manage.py', *args], cwd=ROOT, env=current_env or env,
                                    capture_output=True, text=True, timeout=40)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            return result.stdout

        def fingerprint(current_env=None):
            return subprocess.check_output([PYTHON, str(Path(__file__).resolve()), '--fingerprint'],
                                           cwd=ROOT, env=current_env or env, text=True).strip()

        def get(path, expected=200):
            try:
                response = opener.open(base + path, timeout=15)
            except HTTPError as error:
                response = error
            body = response.read()
            assert response.status == expected, (path, response.status, body[:1000])
            return response, body

        def post(path, values, expected=200, form_path=None):
            _, body = get(form_path or path)
            text = body.decode()
            token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', text)
            assert token, path
            version = re.search(r'name="version" value="([^"]+)"', text)
            data = {'actor': 'HTTP acceptance auditor', 'csrfmiddlewaretoken': html.unescape(token.group(1))}
            if version:
                data['version'] = version.group(1)
            data.update(values)
            try:
                response = opener.open(base + path, urlencode(data, doseq=True).encode(), timeout=15)
            except HTTPError as error:
                response = error
            output = response.read()
            assert response.status == expected, (path, response.status, output[:3000])
            return response.geturl().replace(base, '').split('?')[0], output.decode()

        def start():
            nonlocal server
            server = subprocess.Popen([PYTHON, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'],
                                      cwd=ROOT, env=env, stdout=log, stderr=log)
            for _ in range(100):
                try:
                    get('/')
                    return
                except (URLError, ConnectionError):
                    if server.poll() is not None:
                        log.flush(); log.seek(0)
                        raise AssertionError(log.read())
                    time.sleep(.05)
            raise AssertionError('Server startup timed out')

        def stop():
            nonlocal server
            if server:
                server.terminate()
                server.wait(timeout=15)
                server = None

        def state(path, target, reason='', **extra):
            return post(path + 'state/' + target + '/', {'confirmed': 'on', 'reason': reason, **extra})

        try:
            command('migrate', '--noinput')
            start()
            assert b'Your next audit starts here' in get('/')[1]
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo(env['AUDIT_TIME_ZONE'])).date()
            engagement_data = {'code': 'DEMO-2026', 'title': 'HTTP acceptance engagement', 'client_or_unit': 'Fictional company',
                               'owner': 'Fictional auditor', 'period_start': (today - timedelta(days=90)).isoformat(), 'period_end': today.isoformat(),
                               'scope': 'Identity systems and access review', 'objectives': 'Assess approval and review evidence'}
            ep, _ = post('/engagements/new/', engagement_data)
            state(ep, 'active')
            controls = []
            for name in ['Approvals', 'Quarterly reviews']:
                payload = {'title': name, 'description': 'A fictional control description', 'owner': 'Fictional owner',
                           'risks_addressed': 'Inappropriate access', 'framework_references': 'Internal policy v1, IAM-01',
                           'testing_procedure': 'Inspect selected access records.'}
                path, _ = post(ep + 'control/new/', payload)
                controls.append((path, payload))
            refs = []
            for title, kind, source, system in [('Approvals index', 'url', 'https://example.com/fictional-approvals', ''),
                    ('Review export', 'document_path', '/fictional/quarterly-review.csv', ''),
                    ('Policy ID', 'external_document_id', 'IAM-POL-2026', 'Fictional registry')]:
                path, _ = post(ep + 'evidence/new/', {'title': title, 'description': 'Fictional source for acceptance testing',
                    'type': kind, 'source': source, 'source_system': system, 'owner': 'Fictional reviewer', 'collection_date': today.isoformat()})
                state(path, 'reviewed', reviewer='Fictional reviewer', reviewed_on=today.isoformat(), review_note='Examined this fictional reference.')
                refs.append(path.rstrip('/').split('/')[-1])
            tests = []
            for index, (control_path, _) in enumerate(controls):
                path, _ = post(ep + 'test/new/', {'control': control_path.rstrip('/').split('/')[-1],
                    'tester': 'Fictional auditor', 'execution_date': today.isoformat(), 'procedure_snapshot': 'Inspect sampled approvals and sign-offs.',
                    'sample_description': 'Two records selected from the fictional population of ten.',
                    'work_performed': 'Inspected both selected records and recorded exceptions.',
                    'result': 'effective' if index == 0 else 'ineffective',
                    'conclusion': 'Approvals were supported.' if index == 0 else 'One owner sign-off was absent.', 'evidence': [refs[index]]})
                state(path, 'completed')
                tests.append(path.rstrip('/').split('/')[-1])
            finding_data = {'title': 'Missing owner sign-off', 'severity': 'high', 'severity_rationale': 'Significant exposure to inappropriate access.',
                'condition': 'One review was unsigned.', 'criteria': 'Internal policy requires owner sign-off.',
                'cause': 'Workflow did not enforce sign-off.', 'impact': 'Inappropriate access may remain.',
                'recommendation': 'Require and record owner approval.', 'owner': 'Fictional owner',
                'controls': [controls[1][0].rstrip('/').split('/')[-1]], 'tests': [tests[1]], 'evidence': [refs[1], refs[2]]}
            fp, _ = post(ep + 'finding/new/', finding_data)
            state(fp, 'open')
            action_data = {'finding': fp.rstrip('/').split('/')[-1], 'description': 'Add mandatory owner sign-off.',
                           'owner': 'Fictional action owner', 'due_date': (today - timedelta(days=2)).isoformat()}
            ap, _ = post(ep + 'action/new/', action_data)
            state(ap, 'in_progress')
            post(ep + 'actions/' + ap.rstrip('/').split('/')[-1] + '/progress/',
                 {'author': 'Fictional updater', 'text': 'Workflow change is being tested.'}, form_path=ap)
            assert b'Overdue' in get(ap)[1]
            before = fingerprint()
            stop()
            start()
            assert before == fingerprint(), 'Restart changed persisted records'
            assert b'Workflow change is being tested.' in get(ap)[1]
            print('PASS: empty database, real CSRF-protected forms, linked records and exact persistence after server restart', flush=True)
            engagement_data.update({'executive_summary': 'Approvals passed; one review exception remains with overdue remediation.',
                                    'methodology': 'Inspected two records from a population of ten for each control.'})
            post(ep + 'edit/', engagement_data)
            state(ep, 'in_review')
            state(ep, 'completed')
            md = get(ep + 'export/md/')[1].decode()
            assert 'COMPLETED ENGAGEMENT' in md and 'Overdue' in md and 'fictional/quarterly' in md
            assert 'one review exception' in md
            archive = zipfile.ZipFile(io.BytesIO(get(ep + 'export/csv/')[1]))
            csv_tests = list(csv.DictReader(io.StringIO(archive.read('test.csv').decode('utf-8-sig'))))
            assert len(csv_tests) == 2 and {r['result'] for r in csv_tests} == {'effective', 'ineffective'}
            assert b'COMPLETED ENGAGEMENT' in get(ep + 'report/')[1]
            post(controls[0][0] + 'edit/', controls[0][1], expected=422)
            state(ep, 'active', 'Reopen to record verified remediation')
            closure_path, _ = post(ep + 'evidence/new/', {'title': 'Closure verification', 'description': 'Owner sign-off verified.',
                'type': 'external_document_id', 'source': 'CLOSURE-2026', 'source_system': 'Fictional registry',
                'owner': 'Fictional reviewer', 'collection_date': today.isoformat()})
            state(closure_path, 'reviewed', reviewer='Fictional reviewer', reviewed_on=today.isoformat(), review_note='Verified owner sign-off.')
            closure_id = closure_path.rstrip('/').split('/')[-1]
            state(ap, 'ready_for_verification')
            action_data.update({'closure_verifier': 'Fictional verifier', 'closure_date': today.isoformat(),
                                'closure_conclusion': 'Sign-off is mandatory and the missing approval was obtained.', 'closure_evidence': [closure_id]})
            post(ap + 'edit/', action_data)
            state(ap, 'completed')
            finding_data.update({'resolution_verifier': 'Fictional verifier', 'resolution_date': today.isoformat(),
                                 'resolution_conclusion': 'The observed weakness is corrected.', 'closure_evidence': [closure_id]})
            post(fp + 'edit/', finding_data)
            state(fp, 'resolved')
            assert b'Resolved' in get(fp)[1]
            assert b'The observed weakness is corrected.' in get(ep + 'report/')[1]
            state(ep, 'in_review')
            state(ep, 'completed')
            second_data = engagement_data | {'code': 'SECOND-2026', 'title': 'Isolation test'}
            ep2, _ = post('/engagements/new/', second_data)
            post(ep2 + 'test/new/', {'control': controls[0][0].rstrip('/').split('/')[-1]}, expected=422)
            get(ep2 + 'control/' + controls[0][0].rstrip('/').split('/')[-1] + '/', expected=404)
            print('PASS: report completion with overdue work, immutable completion, explicit reopening, closure, resolution, exports and crafted cross-engagement denial', flush=True)
            before_backup = fingerprint()
            backup_path = temp / 'backup.sqlite3'
            restored_path = temp / 'restored.sqlite3'
            command('backup_audit', str(backup_path))
            stop()
            command('restore_audit', str(backup_path), str(restored_path))
            restored_env = env | {'AUDIT_DB_PATH': str(restored_path)}
            command('migrate', '--noinput', current_env=restored_env)
            assert before_backup == fingerprint(restored_env), 'Restored records differ'
            command('verify_audit', current_env=restored_env)
            env = restored_env
            start()
            assert b'The observed weakness is corrected.' in get(ep + 'report/')[1]
            assert b'COMPLETED ENGAGEMENT' in get(ep + 'export/md/')[1]
            manifest = json.loads(backup_path.with_suffix('.sqlite3.manifest.json').read_text())
            assert manifest['counts']['engagement'] == 2 and manifest['integrity_check'] == 'ok'
            print('PASS: live SQLite backup, independent restore, byte-equivalent record snapshot, integrity/foreign keys, migrations and restored HTTP report', flush=True)
        finally:
            stop()
            log.close()
    print('All end-to-end checks passed. Temporary databases removed; working data was not changed.')


if __name__ == '__main__':
    main()
