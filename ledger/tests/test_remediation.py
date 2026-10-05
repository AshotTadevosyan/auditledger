from unittest.mock import patch
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.core.exceptions import ValidationError
from ledger.tests import test_workflow as workflow
from django.test import TestCase
from ledger.models import Test, Finding, Action, Evidence, ActivityEvent
from ledger import services as s
from ledger.reports import build_report


class RemediationTests(TestCase):
    setUpTestData = classmethod(workflow.WorkflowTests.setUpTestData.__func__)
    setUp = workflow.WorkflowTests.setUp
    change = workflow.WorkflowTests.change
    save = workflow.WorkflowTests.save
    new_reference = workflow.WorkflowTests.new_reference
    review = workflow.WorkflowTests.review
    def close_finding(self):
        reference = self.review(self.new_reference())
        action = self.change(Action.objects.first(), 'ready_for_verification')
        action = self.save(action, {'closure_verifier': self.actor, 'closure_date': self.today,
                                  'closure_conclusion': 'Verified'}, {'closure_evidence': [reference]})
        self.change(action, 'completed')
        finding = self.save(action.finding, {'resolution_verifier': self.actor, 'resolution_date': self.today,
                                           'resolution_conclusion': 'Verified'}, {'closure_evidence': [reference]})
        return self.change(finding, 'resolved')

    def test_resolved_test_guard(self):
        finding = self.close_finding()
        test = finding.tests.first()
        before = s.snapshot(test), test.version, ActivityEvent.objects.count()
        with self.assertRaisesMessage(ValidationError, finding.code):
            self.change(test, 'in_progress', 'Rewrite')
        with self.assertRaisesMessage(ValidationError, finding.code):
            self.save(test, {'work_performed': 'Rewrite'})
        test.refresh_from_db()
        self.assertEqual(before, (s.snapshot(test), test.version, ActivityEvent.objects.count()))
        self.change(finding, 'open', 'Revalidate')
        test = self.change(test, 'in_progress', 'Revalidate')
        self.change(test, 'completed')
        self.change(finding, 'resolved')

    def test_completed_action_support_guard(self):
        support = self.review(self.new_reference('Separate support'))
        self.save(Action.objects.first(), {}, {'evidence': [support]})
        finding = self.close_finding()
        with self.assertRaises(ValidationError):
            self.save(support, {'source': 'CHANGED'})
        with self.assertRaises(ValidationError):
            self.change(support, 'unreviewed', 'Reset')
        support = self.save(support, {'title': 'Correction'})
        self.assertEqual(support.review_status, 'reviewed')
        self.change(finding, 'open', 'Revalidate')
        self.change(Action.objects.first(), 'in_progress', 'Revalidate')
        self.assertEqual(self.save(support, {'source': 'CHANGED'}).review_status, 'unreviewed')

    def test_evidence_query_growth(self):
        def counts():
            with CaptureQueriesContext(connection) as overview:
                self.client.get(self.e.get_absolute_url())
            with CaptureQueriesContext(connection) as report:
                build_report(self.e.pk)
            return len(overview), len(report)
        before = counts()
        for i in range(100):
            self.new_reference(str(i))
        after = counts()
        print('QUERY MEASUREMENTS', before, after)
        self.assertLessEqual(after[0] - before[0], 5)
        self.assertLessEqual(after[1] - before[1], 5)

    def test_multiple_resolved_and_open_findings_protect_test_atomically(self):
        from ledger.schema import FIELDS
        first = Finding.objects.first()
        test = first.tests.first()
        copies = []
        for i in range(2):
            data = {name: getattr(first, name) for name in FIELDS['finding']}
            data['title'] = 'Shared test finding ' + str(i)
            f = s.save_record('finding', data, self.actor, self.e.pk, relations={
                'controls': list(first.controls.all()), 'tests': [test], 'evidence': list(first.evidence.all())})
            f = self.change(f, 'open')
            copies.append(f)
        first = self.close_finding()
        second, opened = copies
        a = s.save_record('action', {'finding': second, 'description': 'Correct shared issue', 'owner': self.actor, 'due_date': self.today}, self.actor, self.e.pk)
        a = self.change(a, 'ready_for_verification')
        reference = first.closure_evidence.first()
        a = self.save(a, {'closure_verifier': self.actor, 'closure_date': self.today, 'closure_conclusion': 'Verified'}, {'closure_evidence': [reference]})
        self.change(a, 'completed')
        second = self.save(second, {'resolution_verifier': self.actor, 'resolution_date': self.today, 'resolution_conclusion': 'Verified'}, {'closure_evidence': [reference]})
        second = self.change(second, 'resolved')
        before = s.snapshot(test), test.version, ActivityEvent.objects.count()
        with self.assertRaises(ValidationError) as caught:
            self.change(test, 'in_progress', 'Rework')
        self.assertIn(first.code, str(caught.exception))
        self.assertIn(second.code, str(caught.exception))
        self.assertNotIn(opened.code, str(caught.exception))
        test.refresh_from_db()
        self.assertEqual(before, (s.snapshot(test), test.version, ActivityEvent.objects.count()))
        self.change(first, 'open', 'Revalidate')
        with self.assertRaisesMessage(ValidationError, second.code):
            self.change(test, 'in_progress', 'Rework')
        self.change(second, 'open', 'Revalidate')
        self.change(test, 'in_progress', 'Rework')

    def test_resolved_supporting_unfinished_test_cannot_be_edited(self):
        first = Finding.objects.first()
        planned = s.save_record('test', {'control': first.controls.first()}, self.actor, self.e.pk)
        self.save(first, {}, {'tests': list(first.tests.all()) + [planned]})
        finding = self.close_finding()
        before = s.snapshot(planned), planned.version, ActivityEvent.objects.count()
        with self.assertRaisesMessage(ValidationError, finding.code):
            self.save(planned, {'work_performed': 'Changed'}, {'evidence': []})
        planned.refresh_from_db()
        self.assertEqual(before, (s.snapshot(planned), planned.version, ActivityEvent.objects.count()))

    def test_stale_procedure_http_and_reconciliation(self):
        from django.urls import reverse
        from ledger.models import Control
        control = Control.objects.first()
        url = reverse('create', args=[self.e.pk, 'test']) + '?control=' + str(control.pk)
        form = self.client.get(url).context['form']
        data = {'control': str(control.pk), 'procedure_snapshot': form['procedure_snapshot'].value(),
                'procedure_source_id': str(control.pk),
                'procedure_source_version': control.version, 'actor': self.actor}
        count = Test.objects.count()
        self.save(control, {'testing_procedure': 'Revised control procedure'})
        before = ActivityEvent.objects.count()
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, data['procedure_snapshot'], status_code=409)
        self.assertEqual(Test.objects.count(), count)
        self.assertEqual(ActivityEvent.objects.count(), before)
        data['procedure_snapshot'] = 'Deliberately customized after comparison'
        data['procedure_reconciled'] = 'on'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertTrue(Test.objects.filter(procedure_snapshot=data['procedure_snapshot']).exists())

    def test_normal_custom_changed_control_and_service_default(self):
        from django.urls import reverse
        from ledger.models import Control
        control, other = list(Control.objects.all())[:2]
        url = reverse('create', args=[self.e.pk, 'test']) + '?control=' + str(control.pk)
        data = {'control': str(control.pk), 'procedure_snapshot': 'Custom procedure', 'actor': self.actor,
                'procedure_source_id': str(control.pk), 'procedure_source_version': control.version}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        data['control'] = str(other.pk)
        self.assertEqual(self.client.post(url, data).status_code, 409)
        data['procedure_reconciled'] = 'on'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        test = s.save_record('test', {'control': control}, self.actor, self.e.pk)
        old = test.procedure_snapshot
        self.save(control, {'testing_procedure': 'New default'})
        test.refresh_from_db()
        self.assertEqual(test.procedure_snapshot, old)
        fresh = s.save_record('test', {'control': control}, self.actor, self.e.pk)
        self.assertEqual(fresh.procedure_snapshot, 'New default')

    def test_rejected_forms_are_dirty_and_contextual_drafts_are_not_created(self):
        from django.urls import reverse
        from django.db import DatabaseError
        test = Test.objects.get(result='ineffective')
        url = reverse('create', args=[self.e.pk, 'finding']) + '?test=' + str(test.pk)
        before = Finding.objects.count()
        response = self.client.get(url)
        form = response.context['form']
        self.assertEqual(form['controls'].value(), [test.control_id])
        self.assertEqual(form['tests'].value(), [test.pk])
        self.assertIn(test.code, str(form['tests']))
        self.assertIn(test.control.title, str(form['tests']))
        self.assertEqual(Finding.objects.count(), before)
        self.assertContains(response, 'data-dirty="false"')
        data = {'title': '', 'condition': 'Retained narrative', 'severity': 'high', 'actor': self.actor}
        self.assertContains(self.client.post(url, data), 'data-dirty="true"', status_code=422)
        data['title'] = 'New finding'
        with patch('ledger.views.services.save_record', side_effect=DatabaseError('Disk full')):
            response = self.client.post(url, data)
        self.assertContains(response, 'Retained narrative', status_code=422)
        self.assertContains(response, 'data-dirty="true"', status_code=422)

    def test_report_presentation_and_complete_machine_history(self):
        import json
        bundle = build_report(self.e.pk)
        self.assertTrue(bundle['traceability'])
        self.assertTrue(any('FND-' in row['findings'] for row in bundle['traceability']))
        action = next(s for s in bundle['sections'] if s['kind'] == 'action')['records'][0]
        self.assertTrue(action['finding_group'])
        self.assertIn('Not applicable in this lifecycle state', [f['label'] for f in action['fields']])
        for event, raw in zip(bundle['history'], bundle['tables']['history']['rows']):
            self.assertEqual(len(event['readable_changes']), len(json.loads(raw['changes'])))

    def test_shared_action_evidence_requires_every_completed_action_reopened(self):
        support = self.review(self.new_reference('Shared action support'))
        closure = self.review(self.new_reference('Distinct closure'))
        first = Action.objects.first()
        second = s.save_record('action', {'finding': first.finding, 'description': 'Second correction', 'owner': self.actor, 'due_date': self.today}, self.actor, self.e.pk)
        for action in [first, second]:
            action = self.change(action, 'ready_for_verification')
            action = self.save(action, {'closure_verifier': self.actor, 'closure_date': self.today, 'closure_conclusion': 'Verified'}, {'evidence': [support], 'closure_evidence': [closure]})
            self.change(action, 'completed')
        before = s.snapshot(support), support.version, ActivityEvent.objects.count()
        for operation in [lambda: self.save(support, {'source': 'Altered'}), lambda: self.change(support, 'unreviewed', 'Reset')]:
            with self.assertRaises(ValidationError) as caught:
                operation()
            self.assertIn(first.code, str(caught.exception))
            self.assertIn(second.code, str(caught.exception))
        support.refresh_from_db()
        self.assertEqual(before, (s.snapshot(support), support.version, ActivityEvent.objects.count()))
        self.change(first, 'in_progress', 'Revalidate')
        with self.assertRaisesMessage(ValidationError, second.code):
            self.save(support, {'source': 'Altered'})
        self.change(second, 'in_progress', 'Revalidate')
        self.assertEqual(self.save(support, {'source': 'Altered'}).review_status, 'unreviewed')

    def test_engagement_reopening_precedes_finding_and_test(self):
        finding = self.close_finding()
        test = finding.tests.first()
        self.e = self.change(self.e, 'in_review')
        self.e = self.change(self.e, 'completed')
        before = ActivityEvent.objects.count()
        with self.assertRaisesMessage(ValidationError, 'engagement is completed'):
            self.change(test, 'in_progress', 'Rework')
        with self.assertRaisesMessage(ValidationError, 'engagement is completed'):
            self.change(finding, 'open', 'Rework')
        self.assertEqual(ActivityEvent.objects.count(), before)
        self.e = self.change(self.e, 'active', 'Revalidate')
        with self.assertRaisesMessage(ValidationError, finding.code):
            self.change(test, 'in_progress', 'Rework')
        self.change(finding, 'open', 'Revalidate')
        self.change(test, 'in_progress', 'Rework')

    def test_unavailable_action_ui_explains_parent_and_register_links_controls(self):
        from django.urls import reverse
        finding = self.close_finding()
        action = finding.actions.first()
        response = self.client.get(action.get_absolute_url())
        self.assertContains(response, 'Open or reopen')
        self.assertNotContains(response, 'Reopen with reason')
        self.assertNotContains(response, 'Edit remediation action')
        response = self.client.get(reverse('register', args=[self.e.pk, 'finding']))
        self.assertContains(response, finding.controls.first().get_absolute_url())
