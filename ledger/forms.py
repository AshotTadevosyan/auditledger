from django import forms
from django.utils import timezone
from .models import MODELS, Evidence
from .schema import FIELDS, RELATIONS


HELP = {
    'code': 'Optional. Leave blank for a permanent generated code. Codes cannot be edited later.',
    'scope': 'Systems, processes, locations and exclusions covered by this engagement.',
    'framework_references': 'Optional context: framework name, version and reference. No compliance inference is made.',
    'procedure_snapshot': 'This test keeps its own procedure. Later control edits do not change it.',
    'sample_description': 'Describe the population and sample, or explain why sampling does not apply.',
    'applicability_or_limitation_rationale': 'Required for not applicable or unable to conclude results.',
    'no_finding_rationale': 'For a partially effective or ineffective result, link a finding or explain why one is not raised.',
    'source': 'Exact reference only. HTTP(S) URLs, document paths and external IDs are never fetched or uploaded.',
    'source_system': 'Required for an external document ID, e.g. the document management system name.',
    'notes': 'Version, page, section or access instructions. Do not enter credentials.',
    'cause': 'If undetermined, explicitly explain why. Do not invent a cause.',
    'severity': 'Critical: urgent substantial exposure. High: significant exposure. Medium: meaningful weakness. Low: limited exposure. Informational: improvement observation.',
    'resolution_date': 'Cannot predate action verification or the related testing.',
    'closure_date': 'Verification must be on or after the ready-for-verification date and related testing.',
}


class RelatedChoice(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if obj.kind == 'test':
            return f'{obj.code} · {obj.control.code} — {obj.control.title} · {obj.execution_date or "Undated"} · {obj.get_result_display() or "No result"} / {obj.get_status_display()}'
        state = getattr(obj, 'review_status', getattr(obj, 'status', ''))
        return f'{obj} [{state.replace("_", " ")}]' if state else str(obj)


class RecordForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)
    actor = forms.CharField(max_length=200, initial='Local auditor', label='Your name / actor label', help_text='Self-asserted label recorded in activity history.')
    reason = forms.CharField(required=False, max_length=20000, widget=forms.Textarea(attrs={'rows': 2}), help_text='Required when changing a remediation due date.')

    def __init__(self, *args, engagement=None, **kwargs):
        super().__init__(*args, **kwargs)
        kind = self.instance.kind
        self.engagement = engagement
        creating = self.instance._state.adding
        self.fields['version'].initial = self.instance.version
        if kind == 'test' and creating:
            self.fields['procedure_source_id'] = forms.UUIDField(required=False, widget=forms.HiddenInput)
            self.fields['procedure_source_version'] = forms.IntegerField(required=False, widget=forms.HiddenInput)
            self.fields['procedure_reconciled'] = forms.BooleanField(required=False, label='I compared the selected control’s current procedure and reconciled this snapshot.', help_text='Required if the prefilled source changed. Your custom procedure will be kept.')
        if kind != 'action' or creating:
            self.fields['reason'].help_text = ''

        if kind == 'engagement' and creating:
            self.fields['code'] = forms.CharField(required=False, max_length=40, help_text=HELP['code'])
            self.order_fields(['code'] + list(self.fields))
        for name, field in self.fields.items():
            if name in HELP:
                field.help_text = HELP[name]
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 4
            if isinstance(field, forms.ModelChoiceField):
                field.queryset = field.queryset.filter(engagement=engagement)
            field.widget.attrs.setdefault('class', 'input')
        for parent in ('control', 'finding'):
            if parent in self.fields and not creating:
                self.fields[parent].disabled = True
        if kind in ('evidence', 'action'):
            self.fields['description'].required = True
        for name, (model, *_rest) in RELATIONS.get(kind, {}).items():
            self.fields[name] = RelatedChoice(queryset=model.objects.filter(engagement=engagement).select_related('control') if name == 'tests' else model.objects.filter(engagement=engagement), required=False,
                                              widget=forms.CheckboxSelectMultiple, label=name.replace('_', ' ').capitalize(),
                                              help_text='Select records within this engagement. Evidence labels show review status.')
            if not creating:
                self.initial[name] = list(getattr(self.instance, name).values_list('pk', flat=True))
        if kind == 'finding':
            self.fields['tests'].help_text = 'Tests are labelled by their owning control. Select every owning control above; selections are retained if validation fails.'
        closure = [n for n in self.fields if n.startswith(('closure_', 'resolution_'))]
        supporting = [n for n in RELATIONS.get(kind, {}) if n not in closure]
        drafting = [n for n in self.fields if n not in closure + supporting + ['actor', 'reason', 'version']]
        self.order_fields(drafting + supporting + closure + ['actor', 'reason', 'version'])
        self.section_starts = {}
        for title, names in [('Drafting', drafting), ('Supporting relationships', supporting), ('Closure verification', closure), ('Save details', ['actor'])]:
            visible = [n for n in names if not self.fields[n].widget.is_hidden]
            if visible:
                self.section_starts[visible[0]] = title

    def clean(self):
        cleaned = super().clean()
        if self.instance.kind == 'test' and self.instance._state.adding:
            source = cleaned.get('procedure_source_id')
            version = cleaned.get('procedure_source_version')
            if bool(source) != bool(version):
                raise forms.ValidationError('The procedure source is incomplete. Reload and reconcile this form.')
        return cleaned



FORM_CLASSES = {kind: type(f'{model.__name__}Form', (RecordForm,), {
    'Meta': type('Meta', (), {'model': model, 'fields': FIELDS[kind]})
}) for kind, model in MODELS.items()}


class TransitionForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    actor = forms.CharField(max_length=200, initial='Local auditor', label='Your name / actor label')
    reason = forms.CharField(required=False, max_length=20000, widget=forms.Textarea(attrs={'rows': 3}))
    confirmed = forms.BooleanField(label='I confirm this change to the named record.')

    def __init__(self, *args, review=False, **kwargs):
        super().__init__(*args, **kwargs)
        if review:
            self.fields['reviewer'] = forms.CharField(max_length=200)
            self.fields['reviewed_on'] = forms.DateField(initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
            self.fields['review_note'] = forms.CharField(max_length=20000, widget=forms.Textarea(attrs={'rows': 3}))
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')
        self.order_fields([f for f in self.fields if f != 'confirmed'] + ['confirmed'])


class ProgressForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    author = forms.CharField(max_length=200, initial='Local auditor')
    text = forms.CharField(max_length=20000, widget=forms.Textarea(attrs={'rows': 4}), label='Progress update')
