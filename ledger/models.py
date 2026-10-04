import uuid
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models import Q, F
from django.urls import reverse
from django.utils import timezone


def choices(*values):
    return [(v, v.replace('_', ' ').capitalize()) for v in values]


def narrative(**kwargs):
    return models.TextField(blank=True, default='', validators=[MaxLengthValidator(20000)], **kwargs)


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    code = models.CharField(max_length=40)

    class Meta:
        abstract = True
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.code} · {getattr(self, "title", getattr(self, "description", ""))[:90]}'

    def get_absolute_url(self):
        if self.kind == 'engagement':
            return reverse('overview', args=[self.pk])
        return reverse('detail', args=[self.engagement_id, self.kind, self.pk])

    def clean(self):
        super().clean()
        errors = {}
        for field in self._meta.fields:
            value = getattr(self, field.attname)
            if isinstance(value, str):
                setattr(self, field.attname, value.strip())
                if value and not field.blank and not value.strip():
                    errors[field.name] = 'This field is required.'
        if errors:
            raise ValidationError(errors)


class Engagement(Record):
    kind = 'engagement'
    STATUS = choices('draft', 'active', 'in_review', 'completed')
    code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=200)
    client_or_unit = models.CharField(max_length=200)
    owner = models.CharField(max_length=200)
    scope = narrative()
    objectives = narrative()
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default='draft')
    methodology = narrative()
    executive_summary = narrative()
    completed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta(Record.Meta):
        constraints = [
            models.CheckConstraint(condition=Q(period_end__gte=F('period_start')), name='engagement_period_order'),
            models.CheckConstraint(condition=Q(status__in=['draft', 'active', 'in_review', 'completed']), name='engagement_state'),
        ]

    def clean(self):
        super().clean()
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValidationError({'period_end': 'End date must be on or after the start date.'})

    @property
    def editable(self):
        return not self.archived_at and self.status in ('draft', 'active')


class ScopedRecord(Record):
    engagement = models.ForeignKey(Engagement, on_delete=models.PROTECT)

    class Meta(Record.Meta):
        abstract = True
        constraints = [models.UniqueConstraint(fields=['engagement', 'code'], name='%(class)s_unique_code')]


class Control(ScopedRecord):
    kind = 'control'
    title = models.CharField(max_length=200)
    description = narrative()
    owner = models.CharField(max_length=200, blank=True)
    risks_addressed = narrative()
    framework_references = narrative()
    testing_procedure = narrative()
    retired_at = models.DateTimeField(null=True, blank=True)
    retirement_reason = narrative()

    @property
    def latest_result(self):
        test = self.test_set.filter(status='completed').order_by('-execution_date', '-created_at', '-id').first()
        return test.get_result_display() if test else 'Not tested'


class Evidence(ScopedRecord):
    kind = 'evidence'
    TYPE = choices('url', 'document_path', 'external_document_id')
    STATUS = choices('unreviewed', 'reviewed', 'rejected')
    title = models.CharField(max_length=200)
    description = narrative()
    type = models.CharField(max_length=25, choices=TYPE)
    source = models.CharField(max_length=2048)
    source_system = models.CharField(max_length=200, blank=True)
    collection_date = models.DateField()
    owner = models.CharField(max_length=200)
    notes = narrative()
    review_status = models.CharField(max_length=15, choices=STATUS, default='unreviewed')
    reviewer = models.CharField(max_length=200, blank=True)
    reviewed_on = models.DateField(null=True, blank=True)
    review_note = narrative()
    rejection_reason = narrative()

    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(type__in=['url', 'document_path', 'external_document_id']), name='evidence_type'),
            models.CheckConstraint(condition=Q(review_status__in=['unreviewed', 'reviewed', 'rejected']), name='evidence_state'),
        ]

    @property
    def safe_url(self):
        try:
            parts = urlsplit(self.source)
            if (self.type == 'url' and parts.scheme.lower() in ('https', 'http') and parts.hostname
                    and not parts.username and not parts.password and not any(ord(c) < 33 for c in self.source)):
                return self.source
        except ValueError:
            pass
        return ''


class Test(ScopedRecord):
    kind = 'test'
    STATUS = choices('planned', 'in_progress', 'completed')
    RESULTS = choices('effective', 'partially_effective', 'ineffective', 'not_applicable', 'unable_to_conclude')
    control = models.ForeignKey(Control, on_delete=models.PROTECT)
    procedure_snapshot = narrative()
    tester = models.CharField(max_length=200, blank=True)
    execution_date = models.DateField(null=True, blank=True)
    sample_description = narrative()
    work_performed = narrative()
    status = models.CharField(max_length=20, choices=STATUS, default='planned')
    result = models.CharField(max_length=25, choices=RESULTS, blank=True)
    conclusion = narrative()
    applicability_or_limitation_rationale = narrative()
    no_finding_rationale = narrative()
    evidence = models.ManyToManyField(Evidence, through='TestEvidence', blank=True, related_name='tests')

    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(status__in=['planned', 'in_progress', 'completed']), name='test_state'),
            models.CheckConstraint(condition=Q(result__in=['', 'effective', 'partially_effective', 'ineffective', 'not_applicable', 'unable_to_conclude']), name='test_result'),
        ]


class Finding(ScopedRecord):
    kind = 'finding'
    STATUS = choices('draft', 'open', 'resolved', 'withdrawn')
    SEVERITY = choices('critical', 'high', 'medium', 'low', 'informational')
    title = models.CharField(max_length=200)
    condition = narrative()
    criteria = narrative()
    cause = narrative()
    impact = narrative()
    severity = models.CharField(max_length=15, choices=SEVERITY, default='medium')
    severity_rationale = narrative()
    recommendation = narrative()
    owner = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default='draft')
    resolution_verifier = models.CharField(max_length=200, blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    resolution_conclusion = narrative()
    withdrawal_reason = narrative()
    controls = models.ManyToManyField(Control, through='FindingControl', blank=True, related_name='findings')
    tests = models.ManyToManyField(Test, through='FindingTest', blank=True, related_name='findings')
    evidence = models.ManyToManyField(Evidence, through='FindingEvidence', blank=True, related_name='findings')
    closure_evidence = models.ManyToManyField(Evidence, through='FindingClosureEvidence', blank=True, related_name='closed_findings')

    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(status__in=['draft', 'open', 'resolved', 'withdrawn']), name='finding_state'),
            models.CheckConstraint(condition=Q(severity__in=['critical', 'high', 'medium', 'low', 'informational']), name='finding_severity'),
        ]


class Action(ScopedRecord):
    kind = 'action'
    STATUS = choices('not_started', 'in_progress', 'blocked', 'ready_for_verification', 'completed')
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT, related_name='actions')
    description = narrative()
    owner = models.CharField(max_length=200)
    due_date = models.DateField()
    status = models.CharField(max_length=25, choices=STATUS, default='not_started')
    blocked_reason = narrative()
    closure_verifier = models.CharField(max_length=200, blank=True)
    closure_date = models.DateField(null=True, blank=True)
    closure_conclusion = narrative()
    ready_at = models.DateTimeField(null=True, blank=True)
    evidence = models.ManyToManyField(Evidence, through='ActionEvidence', blank=True, related_name='actions')
    closure_evidence = models.ManyToManyField(Evidence, through='ActionClosureEvidence', blank=True, related_name='closed_actions')

    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.CheckConstraint(condition=Q(status__in=['not_started', 'in_progress', 'blocked', 'ready_for_verification', 'completed']), name='action_state'),
        ]

    @property
    def overdue(self):
        return self.status != 'completed' and self.due_date < timezone.localdate()


class ProgressUpdate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    engagement = models.ForeignKey(Engagement, on_delete=models.PROTECT)
    action = models.ForeignKey(Action, on_delete=models.PROTECT, related_name='progress_updates')
    author = models.CharField(max_length=200)
    text = models.TextField(validators=[MaxLengthValidator(20000)])
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['recorded_at', 'id']


class ScopedLink(models.Model):
    engagement = models.ForeignKey(Engagement, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class TestEvidence(ScopedLink):
    test = models.ForeignKey(Test, on_delete=models.PROTECT)
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['test', 'evidence'], name='unique_test_evidence')]


class FindingControl(ScopedLink):
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT)
    control = models.ForeignKey(Control, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['finding', 'control'], name='unique_finding_control')]


class FindingTest(ScopedLink):
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT)
    test = models.ForeignKey(Test, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['finding', 'test'], name='unique_finding_test')]


class FindingEvidence(ScopedLink):
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT)
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['finding', 'evidence'], name='unique_finding_evidence')]


class FindingClosureEvidence(ScopedLink):
    finding = models.ForeignKey(Finding, on_delete=models.PROTECT)
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['finding', 'evidence'], name='unique_finding_closure')]


class ActionEvidence(ScopedLink):
    action = models.ForeignKey(Action, on_delete=models.PROTECT)
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['action', 'evidence'], name='unique_action_support')]


class ActionClosureEvidence(ScopedLink):
    action = models.ForeignKey(Action, on_delete=models.PROTECT)
    evidence = models.ForeignKey(Evidence, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['action', 'evidence'], name='unique_action_closure')]


class CodeSequence(models.Model):
    scope = models.CharField(max_length=100, unique=True)
    value = models.PositiveIntegerField(default=0)


class ActivityEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    engagement = models.ForeignKey(Engagement, on_delete=models.PROTECT)
    entity_type = models.CharField(max_length=30)
    entity_id = models.UUIDField()
    entity_code = models.CharField(max_length=40)
    operation = models.CharField(max_length=40)
    actor_label = models.CharField(max_length=200)
    timestamp = models.DateTimeField(default=timezone.now)
    changes = models.JSONField(default=dict)
    reason = narrative()

    class Meta:
        ordering = ['-timestamp', '-id']


MODELS = {m.kind: m for m in [Engagement, Control, Test, Evidence, Finding, Action]}
PREFIXES = {'engagement': 'ENG', 'control': 'CTL', 'test': 'TST', 'evidence': 'EVD', 'finding': 'FND', 'action': 'ACT'}
