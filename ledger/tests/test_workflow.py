import csv
import io
import json
import tempfile
import zipfile
from datetime import date, timedelta, datetime, timezone as dt_timezone
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from ledger import services as s
from ledger.demo import seed_demo
from ledger.models import (Engagement, Control, Test, Evidence, Finding, Action, TestEvidence,
                           FindingControl, FindingTest, FindingEvidence, FindingClosureEvidence,
                           ActionEvidence, ActionClosureEvidence, ProgressUpdate, ActivityEvent)
from ledger.reports import build_report, markdown_report, csv_bundle, csv_safe


class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e, _ = seed_demo()

    def setUp(self):
        self.e = Engagement.objects.get(pk=self.e.pk)
        self.actor = 'Test auditor'
        self.today = timezone.localdate()
        self.client = Client(HTTP_HOST='localhost')

    def change(self, obj, target, reason='', details=None):
        obj.refresh_from_db()
        return s.transition(obj.kind, obj.pk, self.e.pk, obj.version, target, self.actor, reason, details, True)

    def save(self, obj, data, relations=None, reason=''):
        obj.refresh_from_db()
        return s.save_record(obj.kind, data, self.actor, self.e.pk, obj.pk, obj.version, relations, reason)

    def new_engagement(self):
        return s.save_record('engagement', {'title': 'Second engagement', 'client_or_unit': 'Fictional client',
                     'owner': 'Test', 'period_start': self.today, 'period_end': self.today}, self.actor)

    def new_reference(self, suffix='Closure'):
        return s.save_record('evidence', {'title': suffix, 'description': 'Fictional verification reference',
                   'type': 'external_document_id', 'source': 'CLOSE-001', 'source_system': 'Fictional system',
                   'collection_date': self.today, 'owner': self.actor}, self.actor, self.e.pk)

    def review(self, reference):
        return self.change(reference, 'reviewed', details={'reviewer': self.actor, 'reviewed_on': self.today, 'review_note': 'Inspected the reference.'})

    def test_central_completion_reopen_remediation_resolution(self):
        ready = s.readiness(self.e)
        self.assertTrue(ready['completion_ready'])
        self.assertEqual(ready['counts']['overdue'], 1)
        self.assertTrue(ready['warnings'])
        self.e = self.change(self.e, 'in_review')
        self.e = self.change(self.e, 'completed')
        self.assertIsNotNone(self.e.completed_at)
        self.assertFalse(build_report(self.e.pk)['draft'])
        with self.assertRaises(ValidationError):
            self.save(self.e, {'title': 'Silent edit'})
        self.e = self.change(self.e, 'active', 'Reopen for verified remediation')
        reference = self.review(self.new_reference())
        action = Action.objects.get(engagement=self.e)
        action = self.change(action, 'ready_for_verification')
        action = self.save(action, {'closure_verifier': self.actor, 'closure_date': self.today,
                                   'closure_conclusion': 'Owner approval is now mandatory and the missing sign-off was obtained.'},
                                   {'closure_evidence': [reference]})
        action = self.change(action, 'completed')
        finding = action.finding
        finding = self.save(finding, {'resolution_verifier': self.actor, 'resolution_date': self.today,
                            'resolution_conclusion': 'The corrective action addresses the observed weakness.'}, {'closure_evidence': [reference]})
        finding = self.change(finding, 'resolved')
        self.assertEqual(finding.status, 'resolved')
        self.assertEqual(s.readiness(self.e)['counts']['overdue'], 0)
        with self.assertRaises(ValidationError):
            self.change(action, 'in_progress', 'Retry')
        finding = self.change(finding, 'open', 'Additional verification required')
        action = self.change(action, 'in_progress', 'Repeat verification')
        self.assertTrue(action.closure_conclusion)
        report = markdown_report(build_report(self.e.pk))
        self.assertIn('mandatory and the missing sign', report)
        self.assertIn('Additional verification required', report)

    def test_seed_explicit_and_repeat_safe(self):
        before = ActivityEvent.objects.count()
        e, created = seed_demo()
        self.assertFalse(created)
        self.assertEqual(e.pk, self.e.pk)
        self.assertEqual(before, ActivityEvent.objects.count())

    def test_dates_required_fields_duplicate_codes_and_enum_validation(self):
        for data in [{'title': '  '}, {'period_end': self.e.period_start - timedelta(days=1)}]:
            with self.assertRaises(ValidationError):
                self.save(self.e, data)
        with self.assertRaises(ValidationError):
            s.save_record('engagement', {'code': self.e.code, 'title': 'Duplicate', 'client_or_unit': 'Test',
                         'owner': 'Test', 'period_start': self.today, 'period_end': self.today}, self.actor)
        with self.assertRaises(ValidationError):
            self.save(Test.objects.first(), {'result': 'magic'})
        with self.assertRaises(ValidationError):
            s.save_record('finding', {'title': 'Test', 'severity': 'extreme'}, self.actor, self.e.pk)
        self.assertEqual(Engagement.objects.count(), 1)

    def test_activation_and_no_control_readiness(self):
        e = self.new_engagement()
        with self.assertRaises(ValidationError):
            s.transition('engagement', e.pk, e.pk, e.version, 'active', self.actor, confirmed=True)
        self.assertFalse(s.readiness(e)['review_ready'])

    def test_procedure_snapshot_and_latest_result_ties(self):
        control = Control.objects.first()
        old = control.test_set.first().procedure_snapshot
        self.save(control, {'testing_procedure': 'A changed procedure'})
        self.assertEqual(control.test_set.first().procedure_snapshot, old)
        new = s.save_record('test', {'control': control}, self.actor, self.e.pk)
        self.assertEqual(new.procedure_snapshot, 'A changed procedure')
        new = self.save(new, {'tester': self.actor, 'execution_date': self.today, 'sample_description': 'No sample: not applicable.',
                             'work_performed': 'Confirmed system exclusion.', 'result': 'not_applicable', 'conclusion': 'Not applicable to this period.',
                             'applicability_or_limitation_rationale': 'System not deployed in this audit period.'})
        self.change(new, 'completed')
        self.assertEqual(control.latest_result, 'Not applicable')

    def test_incomplete_test_and_review_support_rejected_atomically(self):
        t = s.save_record('test', {'control': Control.objects.first()}, self.actor, self.e.pk)
        before = ActivityEvent.objects.count()
        with self.assertRaises(ValidationError):
            self.change(t, 'completed')
        t.refresh_from_db()
        self.assertEqual(t.status, 'planned')
        self.assertEqual(ActivityEvent.objects.count(), before)
        t = self.save(t, {'tester': self.actor, 'execution_date': self.today, 'sample_description': 'Ten records',
                         'work_performed': 'Inspected records', 'result': 'effective', 'conclusion': 'All sampled items passed'}, {'evidence': [self.new_reference()]})
        with self.assertRaises(ValidationError):
            self.change(t, 'completed')

    def test_not_applicable_and_limitation_require_rationale(self):
        t = self.change(Test.objects.first(), 'in_progress', 'Reassess applicability')
        t = self.save(t, {'result': 'unable_to_conclude', 'applicability_or_limitation_rationale': ''}, {'evidence': []})
        with self.assertRaises(ValidationError):
            self.change(t, 'completed')
        t = self.save(t, {'applicability_or_limitation_rationale': 'Source was unavailable throughout the audit.'})
        t = self.change(t, 'completed')
        self.assertTrue(any('Source was unavailable' in w['message'] for w in s.readiness(self.e)['warnings']))

    def test_evidence_edit_protection_reset_and_title_only(self):
        r = Evidence.objects.filter(tests__result='effective').first()
        r = self.save(r, {'title': 'Corrected title'})
        self.assertEqual(r.review_status, 'reviewed')
        with self.assertRaises(ValidationError):
            self.save(r, {'source': 'https://example.com/changed'})
        test = r.tests.first()
        self.change(test, 'in_progress', 'Source needs correction')
        r = self.save(r, {'source': 'https://example.com/changed'})
        self.assertEqual(r.review_status, 'unreviewed')
        self.assertIsNone(r.reviewed_on)

    def test_review_rejection_correction_and_date_requirements(self):
        r = self.new_reference()
        with self.assertRaises(ValidationError):
            self.change(r, 'reviewed', details={'reviewer': 'Test', 'reviewed_on': self.today + timedelta(days=1), 'review_note': 'Future review'})
        with self.assertRaises(ValidationError):
            self.change(r, 'rejected')
        r = self.change(r, 'rejected', 'Wrong version')
        r = self.change(r, 'unreviewed', 'Corrected reference')
        r = self.review(r)
        self.assertEqual(r.review_status, 'reviewed')
        with self.assertRaises(ValidationError):
            self.save(r, {'collection_date': self.today + timedelta(days=1)})

    def test_unsafe_urls_are_rejected_and_legacy_sources_not_clickable(self):
        for source in ['javascript:alert(1)', 'data:text/html,hello', 'file:///tmp/example', 'https://user:password@example.com', 'https://example.com/\nattack']:
            r = self.new_reference(source[:40])
            with self.assertRaises(ValidationError):
                self.save(r, {'type': 'url', 'source': source})
            r.type, r.source = 'url', source
            self.assertEqual(r.safe_url, '')

    def test_opening_incomplete_finding_fails_and_tests_must_match_controls(self):
        f = s.save_record('finding', {'title': 'Draft', 'severity': 'high'}, self.actor, self.e.pk)
        with self.assertRaises(ValidationError):
            self.change(f, 'open')
        t = Test.objects.first()
        other = Control.objects.exclude(pk=t.control_id).first()
        with self.assertRaises(ValidationError):
            self.save(f, {}, {'controls': [other], 'tests': [t]})
        self.assertFalse(f.tests.exists())
        self.assertFalse(f.controls.exists())

    def test_overdue_boundary_uses_configured_calendar_day(self):
        action = Action.objects.first()
        action = self.save(action, {'due_date': self.today}, reason='Due today boundary')
        self.assertFalse(action.overdue)
        action = self.save(action, {'due_date': self.today - timedelta(days=1)}, reason='Past boundary')
        self.assertTrue(action.overdue)
        with override_settings(TIME_ZONE='Asia/Yerevan'), timezone.override('Asia/Yerevan'):
            with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 3, 22, 30, tzinfo=dt_timezone.utc)):
                action.due_date = date(2026, 10, 3)
                self.assertTrue(action.overdue)
                action.due_date = date(2026, 10, 4)
                self.assertFalse(action.overdue)

    def test_due_date_changes_require_reason_and_progress_is_append_only(self):
        action = Action.objects.first()
        old_date = action.due_date
        with self.assertRaises(ValidationError):
            self.save(action, {'due_date': self.today})
        action.refresh_from_db()
        self.assertEqual(action.due_date, old_date)
        count = action.progress_updates.count()
        s.add_progress(action.pk, self.e.pk, action.version, self.actor, 'Correcting the previous estimate.')
        self.assertEqual(action.progress_updates.count(), count + 1)
        action.refresh_from_db()
        with self.assertRaises(ValidationError):
            s.add_progress(action.pk, self.e.pk, action.version, '  ', '  ')

    def test_shortcut_transitions_and_missing_confirmation_fail(self):
        for obj, target in [(self.e, 'completed'), (Action.objects.first(), 'completed'), (Test.objects.first(), 'planned'), (Finding.objects.first(), 'draft')]:
            with self.assertRaises(ValidationError):
                self.change(obj, target, 'Test')
        with self.assertRaises(ValidationError):
            s.transition('engagement', self.e.pk, self.e.pk, self.e.version, 'in_review', self.actor, confirmed=False)
        with self.assertRaises(ValidationError):
            self.change(Test.objects.first(), 'in_progress')

    def test_action_blocked_rejected_verification_and_invalid_closure(self):
        a = Action.objects.first()
        with self.assertRaises(ValidationError):
            self.change(a, 'blocked')
        a = self.change(a, 'blocked', 'Waiting on owner')
        a = self.change(a, 'in_progress', 'Owner available')
        a = self.change(a, 'ready_for_verification')
        with self.assertRaises(ValidationError):
            self.change(a, 'completed')
        with self.assertRaises(ValidationError):
            self.change(a, 'in_progress')
        a = self.change(a, 'in_progress', 'Verification rejected: incomplete coverage')
        self.assertEqual(a.status, 'in_progress')
        f = Finding.objects.first()
        with self.assertRaises(ValidationError):
            self.change(f, 'resolved')

    def test_failed_test_disposition_drafts_and_retired_findings(self):
        t = Test.objects.get(result='ineffective')
        f = Finding.objects.first()
        self.save(f, {}, {'tests': []})
        self.assertTrue(any('why no finding' in x['message'] for x in s.readiness(self.e)['blockers']))
        self.change(t.control, 'retire', 'System retired')
        self.assertEqual(s.readiness(self.e)['counts']['open_findings'], 1)
        self.assertTrue(any('why no finding' in x['message'] for x in s.readiness(self.e)['blockers']))
        t = self.change(t, 'in_progress', 'Document disposition')
        t = self.save(t, {'no_finding_rationale': 'The observation is handled in the linked control finding.'})
        self.change(t, 'completed')
        self.assertTrue(s.readiness(self.e)['review_ready'])

    def test_archive_and_review_are_read_only_and_reversible(self):
        e = self.new_engagement()
        e = s.transition('engagement', e.pk, e.pk, e.version, 'archive', self.actor, confirmed=True)
        with self.assertRaises(ValidationError):
            s.save_record('control', {'title': 'Blocked'}, self.actor, e.pk)
        e = s.transition('engagement', e.pk, e.pk, e.version, 'unarchive', self.actor, confirmed=True)
        self.assertTrue(e.editable)
        self.e = self.change(self.e, 'in_review')
        with self.assertRaises(ValidationError):
            self.save(Control.objects.first(), {'title': 'Frozen'})
        self.e = self.change(self.e, 'active', 'Review requested changes')
        self.assertTrue(self.e.editable)

    def test_stale_versions_and_history_rollback(self):
        control = Control.objects.first()
        version = control.version
        self.save(control, {'title': 'Updated'})
        before = ActivityEvent.objects.count()
        with self.assertRaises(s.Conflict):
            s.save_record('control', {'title': 'Stale'}, self.actor, self.e.pk, control.pk, version)
        with patch('ledger.services.ActivityEvent.objects.create', side_effect=RuntimeError('Simulated history storage failure')):
            with self.assertRaises(RuntimeError):
                self.save(control, {'title': 'Must roll back'})
        control.refresh_from_db()
        self.assertEqual(control.title, 'Updated')
        self.assertEqual(ActivityEvent.objects.count(), before)

    def test_service_and_database_cross_engagement_protection(self):
        other = self.new_engagement()
        foreign = s.save_record('evidence', {'title': 'Foreign', 'description': 'Different engagement', 'type': 'document_path',
                   'source': '/fictional/other', 'owner': 'Owner', 'collection_date': self.today}, self.actor, other.pk)
        t = self.change(Test.objects.first(), 'in_progress', 'Retest')
        with self.assertRaises(ValidationError):
            self.save(t, {}, {'evidence': [foreign]})
        with self.assertRaises(IntegrityError), transaction.atomic():
            TestEvidence.objects.create(engagement=self.e, test=t, evidence=foreign)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Test.objects.filter(pk=t.pk).update(engagement=other)
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys')
            self.assertEqual(cursor.fetchone()[0], 1)
        with self.assertRaises(ValidationError):
            s.save_record('test', {'control': t.control}, self.actor, other.pk)

    def test_deletion_restrictions_history_and_codes_not_reused(self):
        r = Evidence.objects.filter(tests__isnull=False).first()
        with self.assertRaises(ValidationError):
            s.delete_record('evidence', r.pk, self.e.pk, r.version, self.actor, True)
        draft = self.new_reference()
        pk, code = draft.pk, draft.code
        s.delete_record('evidence', pk, self.e.pk, draft.version, self.actor, True)
        self.assertTrue(ActivityEvent.objects.filter(entity_id=pk, entity_code=code, operation='delete').exists())
        next_ref = self.new_reference('Replacement')
        self.assertNotEqual(next_ref.code, code)

    def test_withdraw_and_reopen_draft_finding(self):
        f = s.save_record('finding', {'title': 'Provisional', 'severity': 'low'}, self.actor, self.e.pk)
        with self.assertRaises(ValidationError):
            self.change(f, 'withdrawn')
        f = self.change(f, 'withdrawn', 'Duplicate observation')
        self.assertIn('Duplicate observation', markdown_report(build_report(self.e.pk)))
        with self.assertRaises(ValidationError):
            self.change(f, 'open', 'Reconsidered but still incomplete')

    def test_all_pages_and_scoped_navigation_render(self):
        urls = ['/', reverse('create_engagement'), self.e.get_absolute_url(), reverse('edit_engagement', args=[self.e.pk]),
                reverse('report', args=[self.e.pk]), reverse('history', args=[self.e.pk])]
        for kind, model in [('control', Control), ('test', Test), ('evidence', Evidence), ('finding', Finding), ('action', Action)]:
            urls += [reverse('register', args=[self.e.pk, kind]), reverse('create', args=[self.e.pk, kind])]
            for obj in model.objects.all():
                urls += [obj.get_absolute_url(), reverse('edit', args=[self.e.pk, kind, obj.pk])]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_browser_form_validation_save_csrf_and_cross_engagement_request(self):
        url = reverse('create_engagement')
        bad = self.client.post(url, {'title': 'Retain this title'})
        self.assertEqual(bad.status_code, 422)
        self.assertContains(bad, 'Retain this title', status_code=422)
        data = {'code': 'FORM-2026', 'title': 'Form creation', 'client_or_unit': 'Fictional', 'owner': 'Owner',
                'period_start': '2026-01-01', 'period_end': '2026-12-31', 'actor': 'Auditor'}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertTrue(Engagement.objects.filter(code='FORM-2026').exists())
        csrf_client = Client(enforce_csrf_checks=True, HTTP_HOST='localhost')
        self.assertEqual(csrf_client.post(url, data).status_code, 403)
        csrf_client.get(url)
        data['code'] = 'FORM-2027'
        data['csrfmiddlewaretoken'] = csrf_client.cookies['csrftoken'].value
        self.assertEqual(csrf_client.post(url, data).status_code, 302)
        other = self.new_engagement()
        create_test = reverse('create', args=[other.pk, 'test'])
        response = self.client.post(create_test, {'control': str(Control.objects.first().pk), 'actor': 'Test'})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Test.objects.filter(engagement=other).exists())
        self.assertEqual(self.client.get(reverse('detail', args=[other.pk, 'control', Control.objects.first().pk])).status_code, 404)

    def test_local_only_hosts_and_state_changing_gets(self):
        self.assertEqual(self.client.get('/', REMOTE_ADDR='192.0.2.20').status_code, 403)
        self.assertEqual(self.client.get('/', HTTP_HOST='evil.example').status_code, 400)
        url = reverse('engagement_transition', args=[self.e.pk, 'in_review'])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.e.refresh_from_db()
        self.assertEqual(self.e.status, 'active')
        response = self.client.get('/')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn("script-src 'self'", response['Content-Security-Policy'])

    def test_exports_escape_unicode_multiline_html_and_formula_payloads(self):
        title = '=HYPERLINK("https://example.com","test")'
        self.save(self.e, {'title': title, 'executive_summary': '<script>alert(1)</script>\n# injected heading\nUnicode: Երևան, "quoted"'})
        bundle = build_report(self.e.pk)
        md = markdown_report(bundle)
        self.assertIn('DRAFT / INCOMPLETE', md)
        self.assertNotIn('<script>', md)
        self.assertNotIn('\n# injected heading', md)
        self.assertIn('Երևան', md)
        self.assertIn('Overdue', md)
        archive = zipfile.ZipFile(io.BytesIO(csv_bundle(bundle)))
        rows = list(csv.DictReader(io.StringIO(archive.read('engagement.csv').decode('utf-8-sig'))))
        self.assertEqual(rows[0]['title'], "'" + title)
        self.assertIn('Unicode: Երևան, "quoted"', rows[0]['executive_summary'])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(archive.read('test.csv').decode('utf-8-sig'))))), 2)
        self.assertIn('action_closure_evidence.csv', archive.namelist())
        self.assertTrue(archive.read('action_closure_evidence.csv').decode('utf-8-sig').startswith('exported_at,'))
        response = self.client.get(reverse('report', args=[self.e.pk]), {'q': 'filters must not affect exports'})
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')
        for prefix in ['', '  ', '\x01\t', '\ufeff', '\u2003']:
            for char in ['=', '+', '-', '@']:
                self.assertTrue(csv_safe(prefix + char + 'FORMULA').startswith("'"))
        self.assertEqual(csv_safe('Plain source'), 'Plain source')

    def test_empty_report_has_headers_and_no_favorable_conclusion(self):
        e = self.new_engagement()
        bundle = build_report(e.pk)
        report = markdown_report(bundle)
        self.assertIn('Not provided', report)
        self.assertIn('No records', report)
        self.assertIn('BLOCKER', report)
        self.assertNotIn('None identified', report)
        archive = zipfile.ZipFile(io.BytesIO(csv_bundle(bundle)))
        for name in ['control.csv', 'test.csv', 'evidence.csv', 'finding.csv', 'action.csv', 'progress_updates.csv']:
            table = list(csv.reader(io.StringIO(archive.read(name).decode('utf-8-sig'))))
            self.assertEqual(len(table), 1)
            self.assertIn('id', table[0])

    def test_exports_and_filter_links(self):
        for format in ('md', 'csv'):
            response = self.client.get(reverse('export', args=[self.e.pk, format]))
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
        for kind, params in [('control', {'tested': 'yes', 'result': 'ineffective'}), ('finding', {'severity': 'high'}),
                             ('evidence', {'unused': 'yes'}), ('action', {'overdue': 'yes', 'due_from': '2020-01-01'})]:
            self.assertEqual(self.client.get(reverse('register', args=[self.e.pk, kind]), params).status_code, 200)

    def test_all_relationship_tables_reject_foreign_engagements_at_database_level(self):
        other = self.new_engagement()
        local = {'control': Control.objects.first(), 'test': Test.objects.first(), 'evidence': Evidence.objects.first(),
                 'finding': Finding.objects.first(), 'action': Action.objects.first()}
        mappings = [(TestEvidence, 'test', 'evidence'), (FindingControl, 'finding', 'control'),
                    (FindingTest, 'finding', 'test'), (FindingEvidence, 'finding', 'evidence'),
                    (FindingClosureEvidence, 'finding', 'evidence'), (ActionEvidence, 'action', 'evidence'),
                    (ActionClosureEvidence, 'action', 'evidence')]
        for model, origin, target in mappings:
            with self.subTest(table=model.__name__), self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.create(engagement=other, **{origin: local[origin], target: local[target]})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProgressUpdate.objects.create(engagement=other, action=local['action'], author='Test', text='Wrong scope')

    def test_verification_cannot_precede_ready_or_testing_and_closure_reference_is_protected(self):
        a = self.change(Action.objects.first(), 'ready_for_verification')
        reference = self.review(self.new_reference())
        a = self.save(a, {'closure_verifier': self.actor, 'closure_date': self.today - timedelta(days=1),
                         'closure_conclusion': 'Verified'}, {'closure_evidence': [reference]})
        with self.assertRaises(ValidationError):
            self.change(a, 'completed')
        a = self.save(a, {'closure_date': self.today + timedelta(days=1)})
        with self.assertRaises(ValidationError):
            self.change(a, 'completed')
        a = self.save(a, {'closure_date': self.today})
        self.change(a, 'completed')
        with self.assertRaises(ValidationError):
            self.save(reference, {'description': 'Changed closure source meaning'})
        with self.assertRaises(ValidationError):
            self.change(reference, 'unreviewed', 'Review reset')

    def test_latest_completed_test_uses_creation_and_id_tie_break(self):
        control = Control.objects.first()
        first = control.test_set.first()
        second = s.save_record('test', {'control': control, 'tester': self.actor,
            'execution_date': first.execution_date, 'sample_description': 'Not applicable: system excluded',
            'work_performed': 'Checked scope exclusion', 'result': 'not_applicable', 'conclusion': 'Excluded',
            'applicability_or_limitation_rationale': 'Outside the approved scope'}, self.actor, self.e.pk)
        second = self.change(second, 'completed')
        self.assertEqual(control.latest_result, 'Not applicable')
        Test.objects.filter(pk=second.pk).update(created_at=first.created_at)
        expected = second.get_result_display() if str(second.pk) > str(first.pk) else first.get_result_display()
        self.assertEqual(control.latest_result, expected)

    def test_progress_failure_rolls_back_update_and_version(self):
        action = Action.objects.first()
        before_count, before_version = action.progress_updates.count(), action.version
        with patch('ledger.services.ActivityEvent.objects.create', side_effect=RuntimeError('Storage failed')):
            with self.assertRaises(RuntimeError):
                s.add_progress(action.pk, self.e.pk, action.version, self.actor, 'Must roll back')
        action.refresh_from_db()
        self.assertEqual(action.version, before_version)
        self.assertEqual(action.progress_updates.count(), before_count)

    def test_limits_and_future_execution(self):
        with self.assertRaises(ValidationError):
            self.save(self.e, {'title': 'x' * 201})
        with self.assertRaises(ValidationError):
            self.save(self.e, {'scope': 'x' * 20001})
        test = self.change(Test.objects.first(), 'in_progress', 'Retest')
        with self.assertRaises(ValidationError):
            self.save(test, {'execution_date': self.today + timedelta(days=1)})
        with self.assertRaises(ValidationError):
            self.save(self.new_reference(), {'source': 'x' * 2049})

    def test_withdrawal_retains_outstanding_actions_and_reopen_reason(self):
        finding = self.change(Finding.objects.first(), 'withdrawn', 'Auditor withdrew after reassessing criteria')
        self.assertEqual(finding.actions.count(), 1)
        self.assertEqual(s.readiness(self.e)['counts']['outstanding'], 1)
        with self.assertRaises(ValidationError):
            self.change(finding, 'open')
        finding = self.change(finding, 'open', 'New information supports the observation')
        self.assertEqual(finding.status, 'open')

    def test_dashboard_attention_and_invalid_id_filters_are_safe(self):
        self.assertEqual([e.pk for e in self.client.get('/', {'attention': 'open'}).context['rows']], [self.e.pk])
        self.assertEqual([e.pk for e in self.client.get('/', {'attention': 'overdue'}).context['rows']], [self.e.pk])
        self.assertEqual(self.client.get(reverse('register', args=[self.e.pk, 'finding']), {'control': 'not-a-uuid'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('register', args=[self.e.pk, 'test']), {'control': 'not-a-uuid'}).status_code, 200)
        self.assertEqual(self.client.get(reverse('register', args=[self.e.pk, 'action']), {'finding': 'not-a-uuid'}).status_code, 200)

    def test_failed_open_finding_link_edit_is_atomic(self):
        finding = Finding.objects.first()
        links = list(finding.evidence.values_list('pk', flat=True))
        history_count = ActivityEvent.objects.count()
        with self.assertRaises(ValidationError):
            self.save(finding, {'impact': 'New impact'}, {'evidence': []})
        finding.refresh_from_db()
        self.assertEqual(list(finding.evidence.values_list('pk', flat=True)), links)
        self.assertNotEqual(finding.impact, 'New impact')
        self.assertEqual(ActivityEvent.objects.count(), history_count)
