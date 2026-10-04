from .models import (Engagement, Control, Test, Evidence, Finding, Action,
                     TestEvidence, FindingControl, FindingTest, FindingEvidence,
                     FindingClosureEvidence, ActionEvidence, ActionClosureEvidence)

FIELDS = {
    'engagement': ['title', 'client_or_unit', 'owner', 'period_start', 'period_end', 'scope', 'objectives', 'methodology', 'executive_summary'],
    'control': ['title', 'description', 'owner', 'risks_addressed', 'framework_references', 'testing_procedure'],
    'test': ['control', 'procedure_snapshot', 'tester', 'execution_date', 'sample_description', 'work_performed', 'result', 'conclusion', 'applicability_or_limitation_rationale', 'no_finding_rationale'],
    'evidence': ['title', 'description', 'type', 'source', 'source_system', 'collection_date', 'owner', 'notes'],
    'finding': ['title', 'severity', 'severity_rationale', 'condition', 'criteria', 'cause', 'impact', 'recommendation', 'owner', 'resolution_verifier', 'resolution_date', 'resolution_conclusion'],
    'action': ['finding', 'description', 'owner', 'due_date', 'closure_verifier', 'closure_date', 'closure_conclusion'],
}
# name -> (target, through, origin foreign key, target foreign key)
RELATIONS = {
    'test': {'evidence': (Evidence, TestEvidence, 'test', 'evidence')},
    'finding': {
        'controls': (Control, FindingControl, 'finding', 'control'),
        'tests': (Test, FindingTest, 'finding', 'test'),
        'evidence': (Evidence, FindingEvidence, 'finding', 'evidence'),
        'closure_evidence': (Evidence, FindingClosureEvidence, 'finding', 'evidence'),
    },
    'action': {
        'evidence': (Evidence, ActionEvidence, 'action', 'evidence'),
        'closure_evidence': (Evidence, ActionClosureEvidence, 'action', 'evidence'),
    },
}
LABELS = {'engagement': 'Engagement', 'control': 'Control', 'test': 'Test', 'evidence': 'Evidence reference', 'finding': 'Finding', 'action': 'Remediation action'}
TABS = [('overview', 'Overview'), ('control', 'Controls & tests'), ('evidence', 'Evidence'), ('finding', 'Findings'), ('action', 'Remediation'), ('report', 'Report'), ('history', 'History')]
