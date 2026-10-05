from urllib.parse import urlencode
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Q, Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from . import services
from .forms import FORM_CLASSES, TransitionForm, ProgressForm
from .models import MODELS, Engagement, Control, Test, Evidence, Finding, Action, ActivityEvent
from .schema import FIELDS, RELATIONS, LABELS, TABS
from .reports import build_report, markdown_report, csv_bundle, safe_filename, REFERENCE_NOTICE, HISTORY_NOTICE


def common_context(request):
    return {'today': timezone.localdate(), 'local_timezone': settings.TIME_ZONE,
            'reference_notice': REFERENCE_NOTICE, 'history_notice': HISTORY_NOTICE,
            'app_version': settings.APP_VERSION}


def context(e, tab, **extra):
    navigation = []
    for key, title in TABS:
        url = reverse(key, args=[e.pk]) if key in ('overview', 'report', 'history') else reverse('register', args=[e.pk, key])
        navigation.append({'key': key, 'title': title, 'url': url})
    return {'engagement': e, 'tab': tab, 'tabs': navigation, **extra}


def model_for(kind):
    if kind not in MODELS or kind == 'engagement':
        raise Http404('Unknown register')
    return MODELS[kind]


def paginated(request, query):
    page = Paginator(query, 20).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return {'page': page, 'querystring': params.urlencode()}


def add_errors(form, error):
    if isinstance(error, services.Conflict):
        form.add_error(None, error)
    elif hasattr(error, 'message_dict'):
        for key, messages in error.message_dict.items():
            form.add_error(key if key in form.fields else None, messages)
    elif isinstance(error, ValidationError):
        form.add_error(None, error)
    else:
        form.add_error(None, 'The database could not save this change. Your input is retained. Check available disk space, database permissions and concurrent edits, then retry.')


def dashboard(request):
    query = Engagement.objects.all()
    archived = request.GET.get('archived', '')
    if archived == 'yes':
        query = query.filter(archived_at__isnull=False)
    elif archived != 'all':
        query = query.filter(archived_at__isnull=True)
    search = request.GET.get('q', '').strip()
    if search:
        query = query.filter(Q(code__icontains=search) | Q(title__icontains=search) | Q(client_or_unit__icontains=search))
    for key in ('status', 'owner'):
        if request.GET.get(key):
            query = query.filter(**{key: request.GET[key]})
    if request.GET.get('attention') == 'open':
        query = query.filter(finding__status='open').distinct()
    elif request.GET.get('attention') == 'overdue':
        query = query.filter(pk__in=Action.objects.filter(due_date__lt=timezone.localdate()).exclude(status='completed').values('engagement_id'))
    query = query.order_by('-created_at', '-id')
    page_ctx = paginated(request, query)
    rows = []
    for e in page_ctx['page']:
        e.open_count = Finding.objects.filter(engagement=e, status='open').count()
        e.overdue_count = Action.objects.filter(engagement=e, due_date__lt=timezone.localdate()).exclude(status='completed').count()
        rows.append(e)
    active = Engagement.objects.filter(archived_at__isnull=True)
    stats = {'engagements': active.count(), 'active': active.filter(status='active').count(),
             'open_findings': Finding.objects.filter(engagement__archived_at__isnull=True, status='open').count(),
             'overdue': Action.objects.filter(engagement__archived_at__isnull=True, due_date__lt=timezone.localdate()).exclude(status='completed').count()}
    return render(request, 'ledger/dashboard.html', {**page_ctx, 'rows': rows, 'stats': stats,
                  'statuses': Engagement.STATUS, 'owners': Engagement.objects.values_list('owner', flat=True).distinct().order_by('owner')})


def overview(request, engagement_id):
    e = get_object_or_404(Engagement, pk=engagement_id)
    return render(request, 'ledger/overview.html', context(e, 'overview', ready=services.readiness(e), operations=operations(e),
                  recent=e.activityevent_set.all()[:5]))


SEARCH = {
    'control': ['code', 'title', 'description', 'risks_addressed', 'framework_references'],
    'test': ['code', 'procedure_snapshot', 'work_performed', 'conclusion', 'tester'],
    'evidence': ['code', 'title', 'description', 'source', 'source_system'],
    'finding': ['code', 'title', 'condition', 'criteria', 'cause', 'impact', 'recommendation'],
    'action': ['code', 'description', 'owner'],
}


def register(request, engagement_id, kind):
    model = model_for(kind)
    e = get_object_or_404(Engagement, pk=engagement_id)
    query = model.objects.filter(engagement=e)
    search = request.GET.get('q', '').strip()
    if search:
        predicate = Q()
        for name in SEARCH[kind]:
            predicate |= Q(**{f'{name}__icontains': search})
        query = query.filter(predicate)
    filters = []
    def select(name, label, options, field=None):
        nonlocal query
        filters.append({'name': name, 'label': label, 'options': options, 'value': request.GET.get(name, '')})
        if request.GET.get(name):
            allowed = {str(value) for value, _ in options}
            query = query.filter(**{field or name: request.GET[name]}) if request.GET[name] in allowed else query.none()
    if kind != 'test':
        select('owner', 'Owner', [(v, v) for v in model.objects.filter(engagement=e).values_list('owner', flat=True).distinct().order_by('owner') if v])
    if kind in ('test', 'finding', 'action'):
        select('status', 'Status', model.STATUS)
    if kind == 'control':
        filters += [ {'name': 'retired', 'label': 'Disposition', 'options': [('active', 'Active'), ('retired', 'Retired')], 'value': request.GET.get('retired', '')},
                     {'name': 'tested', 'label': 'Testing', 'options': [('yes', 'Has completed tests'), ('no', 'Untested')], 'value': request.GET.get('tested', '')},
                     {'name': 'result', 'label': 'Latest result', 'options': Test.RESULTS, 'value': request.GET.get('result', '')}]
        if request.GET.get('retired'):
            query = query.filter(retired_at__isnull=request.GET['retired'] == 'active')
        if request.GET.get('tested'):
            ids = Test.objects.filter(engagement=e, status='completed').values_list('control_id', flat=True)
            query = query.filter(pk__in=ids) if request.GET['tested'] == 'yes' else query.exclude(pk__in=ids)
        if request.GET.get('result'):
            from django.db.models import OuterRef, Subquery
            latest = Test.objects.filter(control_id=OuterRef('pk'), status='completed').order_by('-execution_date', '-created_at', '-id')
            query = query.annotate(latest_value=Subquery(latest.values('result')[:1])).filter(latest_value=request.GET['result'])
    if kind == 'test':
        select('result', 'Result', Test.RESULTS)
        select('control', 'Control', [(str(c.pk), str(c)) for c in Control.objects.filter(engagement=e)])
    if kind == 'evidence':
        select('type', 'Reference type', Evidence.TYPE)
        select('review_status', 'Review status', Evidence.STATUS)
        filters.append({'name': 'unused', 'label': 'Usage', 'options': [('yes', 'Unused only')], 'value': request.GET.get('unused', '')})
        if request.GET.get('unused') == 'yes':
            query = query.filter(tests__isnull=True, findings__isnull=True, closed_findings__isnull=True, actions__isnull=True, closed_actions__isnull=True)
    if kind == 'finding':
        select('severity', 'Severity', Finding.SEVERITY)
        select('control', 'Related control', [(str(c.pk), str(c)) for c in Control.objects.filter(engagement=e)], 'controls')
    if kind == 'action':
        select('finding', 'Finding', [(str(f.pk), str(f)) for f in Finding.objects.filter(engagement=e)])
        filters.append({'name': 'overdue', 'label': 'Due status', 'options': [('yes', 'Overdue only')], 'value': request.GET.get('overdue', '')})
        if request.GET.get('overdue') == 'yes':
            query = query.filter(due_date__lt=timezone.localdate()).exclude(status='completed')
        for key, lookup in [('due_from', 'due_date__gte'), ('due_to', 'due_date__lte')]:
            if request.GET.get(key):
                try:
                    from datetime import date
                    query = query.filter(**{lookup: date.fromisoformat(request.GET[key])})
                except ValueError:
                    pass
    query = query.distinct().order_by('code', 'id')
    page_ctx = paginated(request, query)
    table = []
    headings = {
        'control': ['Control', 'Owner', 'Framework references', 'Latest completed result', 'Disposition'],
        'test': ['Test', 'Control', 'Tester', 'Execution', 'Result / state'],
        'evidence': ['Reference', 'Type', 'Source', 'Owner', 'Review'],
        'finding': ['Finding', 'Related controls', 'Severity', 'Owner', 'Actions', 'Status'],
        'action': ['Action', 'Finding', 'Owner', 'Due date', 'Status'],
    }[kind]
    for obj in page_ctx['page']:
        title = getattr(obj, 'title', getattr(obj, 'description', obj.code))
        cells = [{'text': title, 'code': obj.code, 'url': obj.get_absolute_url()}]
        if kind == 'control':
            cells += [{'text': obj.owner or 'Not provided'}, {'text': obj.framework_references or 'Not provided'}, {'text': obj.latest_result}, {'text': 'Retired' if obj.retired_at else 'Active', 'badge': 'neutral'}]
        elif kind == 'test':
            cells += [{'text': obj.control.code, 'url': obj.control.get_absolute_url()}, {'text': obj.tester or 'Not provided'}, {'text': obj.execution_date or 'Not provided'}, {'text': (obj.get_result_display() or 'No result') + ' · ' + obj.get_status_display(), 'badge': obj.status}]
        elif kind == 'evidence':
            cells += [{'text': obj.get_type_display()}, {'text': obj.source}, {'text': obj.owner}, {'text': obj.get_review_status_display(), 'badge': obj.review_status}]
        elif kind == 'finding':
            cells += [{'links': list(obj.controls.all())}]
            cells += [{'text': obj.get_severity_display(), 'badge': obj.severity}, {'text': obj.owner or 'Not provided'}, {'text': str(obj.actions.count()), 'url': reverse('register', args=[e.pk, 'action']) + '?' + urlencode({'finding': obj.pk})}, {'text': obj.get_status_display(), 'badge': obj.status}]
        else:
            cells += [{'text': obj.finding.code, 'url': obj.finding.get_absolute_url()}, {'text': obj.owner}, {'text': obj.due_date.isoformat() + (' · Overdue' if obj.overdue else ''), 'badge': 'overdue' if obj.overdue else ''}, {'text': obj.get_status_display(), 'badge': obj.status}]
        table.append(cells)
    return render(request, 'ledger/register.html', context(e, 'control' if kind == 'test' else kind,
                  kind=kind, label=LABELS[kind], headings=headings, table=table, filters=filters,
                  has_records=model.objects.filter(engagement=e).exists(), **page_ctx))


def operations(obj):
    result = []
    def add(target, label):
        url = reverse('engagement_transition', args=[obj.pk, target]) if obj.kind == 'engagement' else reverse('transition', args=[obj.engagement_id, obj.kind, obj.pk, target])
        result.append({'url': url, 'label': label})
    if obj.kind == 'engagement':
        if obj.archived_at:
            add('unarchive', 'Unarchive engagement')
            return result
        labels = {'active': 'Activate engagement' if obj.status == 'draft' else 'Reopen / return to active', 'in_review': 'Submit for review', 'completed': 'Complete engagement'}
        for target in services.TRANSITIONS['engagement'][obj.status]:
            add(target, labels[target])
        if obj.status in ('draft', 'completed'):
            add('archive', 'Archive engagement')
        return result
    if obj.kind == 'action' and obj.finding.status != 'open':
        return result
    if not obj.engagement.editable:
        return result
    if obj.kind == 'control':
        add('restore' if obj.retired_at else 'retire', 'Restore control' if obj.retired_at else 'Retire control')
    else:
        state = obj.review_status if obj.kind == 'evidence' else obj.status
        for target in services.TRANSITIONS[obj.kind].get(state, []):
            label = 'Mark ' + target.replace('_', ' ')
            if state in ('completed', 'resolved', 'withdrawn'):
                label = 'Reopen with reason'
            elif obj.kind == 'evidence' and target == 'unreviewed':
                label = 'Reset review with reason'
            add(target, label)
    return result


def detail(request, engagement_id, kind, pk):
    model = model_for(kind)
    e = get_object_or_404(Engagement, pk=engagement_id)
    obj = get_object_or_404(model, pk=pk, engagement=e)
    fields = []
    for name in FIELDS[kind]:
        value = getattr(obj, name)
        field = obj._meta.get_field(name)
        if field.choices:
            value = getattr(obj, f'get_{name}_display')()
        fields.append({'label': str(field.verbose_name).replace('_', ' ').capitalize(), 'value': value,
                       'url': value.get_absolute_url() if hasattr(value, 'get_absolute_url') else ''})
    related = []
    for name in RELATIONS.get(kind, {}):
        related.append({'label': name.replace('_', ' ').capitalize(), 'records': getattr(obj, name).all()})
    if kind == 'control':
        related += [{'label': 'Test history', 'records': obj.test_set.all()}, {'label': 'Related findings', 'records': obj.findings.all()}]
    if kind == 'test':
        related += [{'label': 'Related findings', 'records': obj.findings.all()}]
    if kind == 'finding':
        related += [{'label': 'Remediation actions', 'records': obj.actions.all()}]
    if kind == 'evidence':
        related += [{'label': 'Used by', 'records': services.evidence_usage(obj)}]
        fields += [{'label': 'Reviewer', 'value': obj.reviewer}, {'label': 'Review date', 'value': obj.reviewed_on}, {'label': 'Review note', 'value': obj.review_note}, {'label': 'Rejection reason', 'value': obj.rejection_reason}]
    can_edit = e.editable and not (kind in ('test', 'action') and obj.status == 'completed') and not (kind == 'finding' and obj.status in ('resolved', 'withdrawn'))
    if kind == 'action' and obj.finding.status != 'open':
        can_edit = False
    return render(request, 'ledger/detail.html', context(e, 'control' if kind == 'test' else kind,
                  obj=obj, kind=kind, label=LABELS[kind], fields=fields, related=related, operations=operations(obj),
                  can_edit=can_edit, issues=services.entity_errors(obj),
                  events=e.activityevent_set.filter(entity_id=obj.pk)[:10],
                  progress_form=ProgressForm(initial={'version': obj.version}) if kind == 'action' else None))


@require_http_methods(['GET', 'POST'])
def edit(request, engagement_id=None, kind='engagement', pk=None):
    if kind not in MODELS:
        raise Http404()
    e = get_object_or_404(Engagement, pk=engagement_id) if engagement_id else None
    obj = get_object_or_404(MODELS[kind], pk=pk, **({'engagement': e} if kind != 'engagement' else {})) if pk else MODELS[kind]()
    if kind == 'engagement' and pk:
        e = obj
    initial = {}
    for parent in ('control', 'finding'):
        if request.GET.get(parent) and parent in FIELDS[kind]:
            parent_obj = get_object_or_404(MODELS[parent], pk=request.GET[parent], engagement=e)
            initial[parent] = parent_obj
            if kind == 'test':
                initial['procedure_snapshot'] = parent_obj.testing_procedure
                initial['procedure_source_id'] = parent_obj.pk
                initial['procedure_source_version'] = parent_obj.version
    if kind == 'finding' and not pk and request.GET.get('test'):
        source_test = get_object_or_404(Test, pk=request.GET['test'], engagement=e)
        initial.update(controls=[source_test.control_id], tests=[source_test.pk], evidence=list(source_test.evidence.all()))
    form = FORM_CLASSES[kind](request.POST or None, instance=obj, engagement=e, initial=initial)
    response_status = 200
    if request.method == 'POST' and form.is_valid():
        data = {name: form.cleaned_data[name] for name in FIELDS[kind]}
        if 'code' in form.cleaned_data:
            data['code'] = form.cleaned_data['code']
        relations = {name: list(form.cleaned_data[name]) for name in RELATIONS.get(kind, {})}
        try:
            saved = services.save_record(kind, data, form.cleaned_data['actor'], e.pk if e else None, pk,
                                         form.cleaned_data['version'], relations, form.cleaned_data['reason'],
                                         procedure_source=(form.cleaned_data.get('procedure_source_id'), form.cleaned_data.get('procedure_source_version'), form.cleaned_data.get('procedure_reconciled')) if kind == 'test' and not pk and form.cleaned_data.get('procedure_source_id') else None)
            return redirect(saved.get_absolute_url() + '?saved=1')
        except (ValidationError, DatabaseError) as error:
            add_errors(form, error)
            response_status = 409 if isinstance(error, services.Conflict) else 422
    elif request.method == 'POST':
        response_status = 422
    ctx = {'form': form, 'kind': kind, 'label': LABELS[kind], 'obj': obj if pk else None,
           'creating': not pk, 'cancel_url': obj.get_absolute_url() if pk else e.get_absolute_url() if e else reverse('dashboard')}
    if e:
        ctx = context(e, 'overview' if kind == 'engagement' else 'control' if kind == 'test' else kind, **ctx)
    return render(request, 'ledger/form.html', ctx, status=response_status)


@require_http_methods(['GET', 'POST'])
def transition_view(request, engagement_id, target, kind='engagement', pk=None):
    e = get_object_or_404(Engagement, pk=engagement_id)
    obj = e if kind == 'engagement' else get_object_or_404(model_for(kind), pk=pk, engagement=e)
    form = TransitionForm(request.POST or None, initial={'version': obj.version}, review=kind == 'evidence' and target == 'reviewed')
    status = 200
    if request.method == 'POST' and form.is_valid():
        try:
            services.transition(kind, obj.pk, e.pk, form.cleaned_data['version'], target, form.cleaned_data['actor'],
                                form.cleaned_data['reason'], form.cleaned_data, form.cleaned_data['confirmed'])
            return redirect(obj.get_absolute_url() + '?saved=1')
        except (ValidationError, DatabaseError) as error:
            add_errors(form, error)
            status = 409 if isinstance(error, services.Conflict) else 422
    return render(request, 'ledger/transition.html', context(e, 'overview' if kind == 'engagement' else kind,
                  form=form, obj=obj, target=target.replace('_', ' '), kind=kind,
                  ready=services.readiness(e) if kind == 'engagement' else None), status=status)


@require_http_methods(['GET', 'POST'])
def delete_view(request, engagement_id, kind, pk):
    e = get_object_or_404(Engagement, pk=engagement_id)
    obj = get_object_or_404(model_for(kind), pk=pk, engagement=e)
    form = TransitionForm(request.POST or None, initial={'version': obj.version})
    if request.method == 'POST' and form.is_valid():
        try:
            services.delete_record(kind, pk, e.pk, form.cleaned_data['version'], form.cleaned_data['actor'], form.cleaned_data['confirmed'])
            return redirect(reverse('register', args=[e.pk, kind]) + '?saved=1')
        except (ValidationError, DatabaseError) as error:
            add_errors(form, error)
    return render(request, 'ledger/transition.html', context(e, kind, form=form, obj=obj, target='delete', kind=kind,
                  dependencies=services.dependencies(obj)))


@require_http_methods(['POST'])
def progress(request, engagement_id, pk):
    e = get_object_or_404(Engagement, pk=engagement_id)
    obj = get_object_or_404(Action, pk=pk, engagement=e)
    form = ProgressForm(request.POST)
    if form.is_valid():
        try:
            services.add_progress(pk, engagement_id, form.cleaned_data['version'], form.cleaned_data['author'], form.cleaned_data['text'])
            return redirect(obj.get_absolute_url() + '?saved=1')
        except (ValidationError, DatabaseError) as error:
            add_errors(form, error)
    return render(request, 'ledger/form.html', context(e, 'action', form=form, label='Progress update', cancel_url=obj.get_absolute_url()), status=422)


def report(request, engagement_id, format=None):
    get_object_or_404(Engagement, pk=engagement_id)
    try:
        bundle = build_report(engagement_id)
        if format == 'md':
            response = HttpResponse(markdown_report(bundle), content_type='text/markdown; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{safe_filename(bundle, "md")}"'
            return response
        if format == 'csv':
            response = HttpResponse(csv_bundle(bundle), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{safe_filename(bundle, "zip")}"'
            return response
        return render(request, 'ledger/report.html', context(bundle['engagement'], 'report', report=bundle, ready=bundle['readiness']))
    except DatabaseError:
        return render(request, 'ledger/error.html', {'message': 'Report generation failed. Check database access and retry; no report was created.'}, status=503)


def history(request, engagement_id):
    e = get_object_or_404(Engagement, pk=engagement_id)
    query = e.activityevent_set.all()
    for field in ('entity_type', 'operation'):
        if request.GET.get(field):
            query = query.filter(**{field: request.GET[field]})
    return render(request, 'ledger/history.html', context(e, 'history', **paginated(request, query),
                  entity_types=MODELS.keys(), operations=e.activityevent_set.values_list('operation', flat=True).distinct().order_by('operation')))
