"""Fictional, explicitly requested demonstration data; never called at startup."""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Engagement
from .services import save_record, transition, add_progress


@transaction.atomic
def seed_demo(code='DEMO-2026'):
    existing = Engagement.objects.filter(code=code).first()
    if existing:
        return existing, False
    today = timezone.localdate()
    actor = 'Morgan Vale (fictional)'
    e = save_record('engagement', {
        'code': code, 'title': 'Identity & access management review', 'client_or_unit': 'Northstar Systems · Fictional demonstration',
        'owner': actor, 'period_start': today - timedelta(days=90), 'period_end': today - timedelta(days=1),
        'scope': 'Corporate identity services, privileged access and quarterly access reviews. Customer environments are excluded.',
        'objectives': 'Evaluate whether access is approved, periodically reviewed and removed when no longer required.',
        'methodology': 'Inspected three reference sources and tested a fictional sample of 12 privileged access records and two quarterly reviews. Results are limited to the described sample and period.',
        'executive_summary': 'Privileged access approvals were supported in the tested sample. One quarterly access review lacked a recorded owner sign-off. Management has an outstanding remediation action; the audit conclusion does not imply certification or compliance.',
    }, actor)
    e = transition('engagement', e.pk, e.pk, e.version, 'active', actor, confirmed=True)
    controls = []
    for title, description, risks, procedure, reference in [
        ('Privileged access is approved', 'Administrators require documented approval before elevated access is provisioned.', 'Unauthorized privileged access.', 'Inspect approvals for 12 sampled privileged accounts and compare approval dates with provisioning dates.', 'Illustrative internal policy IAM-01 v1'),
        ('Quarterly access reviews are signed off', 'System owners review access and retain a dated approval each quarter.', 'Inappropriate access remains undetected.', 'Inspect the two latest quarterly reviews and verify documented owner sign-off.', 'Illustrative internal policy IAM-02 v1'),
    ]:
        controls.append(save_record('control', {'title': title, 'description': description, 'owner': 'Jordan Reed (fictional)',
                     'risks_addressed': risks, 'testing_procedure': procedure, 'framework_references': reference}, actor, e.pk))
    evidence = []
    for title, kind, source, system, description in [
        ('Privileged access approval index', 'url', 'https://example.com/fictional-audit/approvals', '', 'Fictional index for the sampled account approvals.'),
        ('Q2 access review register', 'document_path', '/fictional/evidence/access-review-q2.csv', '', 'Fictional review register showing a missing owner sign-off.'),
        ('Access governance policy', 'external_document_id', 'POL-IAM-2026-001', 'Fictional policy library', 'Fictional policy defining review frequency and ownership.'),
    ]:
        r = save_record('evidence', {'title': title, 'description': description, 'type': kind, 'source': source,
                        'source_system': system, 'collection_date': today - timedelta(days=3), 'owner': actor}, actor, e.pk)
        r = transition('evidence', r.pk, e.pk, r.version, 'reviewed', actor,
                       details={'reviewer': actor, 'reviewed_on': today - timedelta(days=2),
                                'review_note': 'Examined the fictional reference for this demonstration; no document is stored here.'}, confirmed=True)
        evidence.append(r)
    tests = []
    for i, control in enumerate(controls):
        test = save_record('test', {'control': control, 'tester': actor, 'execution_date': today - timedelta(days=2),
                    'sample_description': '12 privileged accounts from a fictional population of 40.' if i == 0 else 'Two quarterly reviews from the audit period.',
                    'work_performed': 'Compared approval and provisioning dates for the selected accounts.' if i == 0 else 'Inspected the two review records for a dated owner sign-off.',
                    'result': 'effective' if i == 0 else 'ineffective',
                    'conclusion': 'The 12 sampled approvals preceded access provisioning.' if i == 0 else 'One of two reviews lacked a recorded owner sign-off.'},
                    actor, e.pk, relations={'evidence': [evidence[i]]})
        tests.append(transition('test', test.pk, e.pk, test.version, 'completed', actor, confirmed=True))
    finding = save_record('finding', {'title': 'Quarterly access review lacks owner sign-off', 'severity': 'high',
                'severity_rationale': 'A missing ownership checkpoint creates significant exposure to inappropriate access.',
                'condition': 'One of two sampled reviews had no recorded owner sign-off.',
                'criteria': 'The internal policy requires a dated system-owner approval for each quarterly review.',
                'cause': 'The review workflow had no mandatory approval step before closure.',
                'impact': 'Inappropriate access could persist without an accountable review decision.',
                'recommendation': 'Require owner sign-off and verify completion before closing each review.',
                'owner': 'Jordan Reed (fictional)'}, actor, e.pk,
                relations={'controls': [controls[1]], 'tests': [tests[1]], 'evidence': [evidence[1], evidence[2]]})
    finding = transition('finding', finding.pk, e.pk, finding.version, 'open', actor, confirmed=True)
    action = save_record('action', {'finding': finding, 'description': 'Add a mandatory owner approval step and complete the missing review sign-off.',
                         'owner': 'Casey Lane (fictional)', 'due_date': today - timedelta(days=7)}, actor, e.pk)
    action = transition('action', action.pk, e.pk, action.version, 'in_progress', actor, confirmed=True)
    add_progress(action.pk, e.pk, action.version, actor, 'The revised workflow is in testing. Owner sign-off for the outstanding review is scheduled.')
    return e, True
