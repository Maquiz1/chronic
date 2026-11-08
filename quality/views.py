from collections import OrderedDict

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from accounts.mixins import RoleRequiredMixin
from accounts.roles import user_can
from crf import spec
from crf.forms import QueryForm
from crf.models import Participant
from crf.views import ENTRY_CODES, participants_with_sections

from . import checks
from .models import DataQuery


def _safe_next(request, fallback):
    nxt = request.POST.get('next', '')
    return nxt if nxt.startswith('/') and not nxt.startswith('//') else fallback


class OverviewView(RoleRequiredMixin, TemplateView):
    """Completeness of every participant by section, with check and query counts."""

    action = 'view_quality'
    template_name = 'quality/overview.html'

    def get_context_data(self, **kwargs):
        open_q = {}
        for pid in DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', flat=True):
            open_q[pid] = open_q.get(pid, 0) + 1
        rows = []
        show = self.request.GET.get('show', 'incomplete')
        for p in participants_with_sections():
            v = p.values()
            status = checks.record_status(v)
            issues = checks.all_issues(v)
            if show == 'incomplete' and status['complete'] and not issues and not open_q.get(p.pk):
                continue
            rows.append({'p': p, 'status': status,
                         'sections': [s for s in status['sections'] if s['state'] != 'calculated'],
                         'errors': sum(1 for i in issues if i.level == checks.ERROR),
                         'warnings': sum(1 for i in issues if i.level == checks.WARNING),
                         'queries': open_q.get(p.pk, 0)})
        return {**super().get_context_data(**kwargs), 'rows': rows, 'show': show, 'entry_codes': ENTRY_CODES}


class PendingView(RoleRequiredMixin, TemplateView):
    """What is still missing, grouped by question: e.g. which participants still wait for an INR result."""

    action = 'view_quality'
    template_name = 'quality/pending.html'

    def get_context_data(self, **kwargs):
        section_filter = self.request.GET.get('section', 'G')
        groups = OrderedDict()
        for _s, f in spec.all_fields():
            if section_filter and _s.code != section_filter:
                continue
            groups[f.name] = {'f': f, 'section': _s, 'participants': []}
        for p in participants_with_sections().filter(locked=False):
            v = p.values()
            for code in ([section_filter] if section_filter else ENTRY_CODES):
                if code not in ENTRY_CODES:
                    continue
                st = checks.section_status(code, v)
                if st['state'] == 'not_started':
                    for f in spec.SECTION_BY_CODE[code].fields:
                        if f.expected and spec.is_relevant(f, v) and not checks.is_answered(f, v):
                            groups[f.name]['participants'].append((p, True))
                    continue
                for f in st['missing']:
                    groups[f.name]['participants'].append((p, False))
        groups = [g for g in groups.values() if g['participants']]
        return {**super().get_context_data(**kwargs), 'groups': groups, 'section_filter': section_filter,
                'sections': [s for s in spec.SECTIONS if s.fields]}


class IssuesView(RoleRequiredMixin, TemplateView):
    """Automatic range and consistency checks across all participants."""

    action = 'view_quality'
    template_name = 'quality/issues.html'

    def get_context_data(self, **kwargs):
        level = self.request.GET.get('level', '')
        queried = set(DataQuery.objects.exclude(status=DataQuery.Status.CLOSED)
                      .values_list('participant_id', 'field', 'rule'))
        rows = []
        for p in participants_with_sections():
            for issue in checks.all_issues(p.values()):
                if level and issue.level != level:
                    continue
                rows.append({'p': p, 'issue': issue, 'queried': (p.pk, issue.field, issue.rule) in queried})
        rows.sort(key=lambda r: (r['issue'].level != checks.ERROR, r['p'].study_id))
        return {**super().get_context_data(**kwargs), 'rows': rows, 'level': level}


class QueryListView(RoleRequiredMixin, ListView):
    action = 'view_quality'
    template_name = 'quality/queries.html'
    paginate_by = 50

    def get_queryset(self):
        qs = DataQuery.objects.select_related('participant', 'raised_by', 'answered_by', 'closed_by')
        status = self.request.GET.get('status', 'open')
        if status in DataQuery.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', 'open')
        ctx['counts'] = {s: DataQuery.objects.filter(status=s).count() for s in DataQuery.Status.values}
        return ctx


class QueryCreateView(RoleRequiredMixin, View):
    action = 'raise_query'

    def post(self, request, pk):
        participant = get_object_or_404(Participant, pk=pk)
        form = QueryForm(request.POST)
        if form.is_valid():
            DataQuery.objects.create(participant=participant, section=form.cleaned_data['section'],
                                     field=form.cleaned_data['field'], message=form.cleaned_data['message'],
                                     rule=request.POST.get('rule', '')[:30], raised_by=request.user)
            messages.success(request, f'Query raised on {participant}.')
        else:
            messages.error(request, 'Query not raised: a message is required.')
        return redirect(_safe_next(request, f'/records/{participant.pk}/'))


class QueryAnswerView(RoleRequiredMixin, View):
    action = 'answer_query'

    def post(self, request, pk):
        query = get_object_or_404(DataQuery, pk=pk)
        response = request.POST.get('response', '').strip()
        if not response:
            messages.error(request, 'Write what was checked or corrected.')
        elif query.status == DataQuery.Status.CLOSED:
            messages.error(request, 'This query is already closed.')
        else:
            query.response, query.status = response, DataQuery.Status.ANSWERED
            query.answered_by, query.answered_at = request.user, timezone.now()
            query.save()
            messages.success(request, 'Answer saved. A Data Manager will review and close the query.')
        return redirect(_safe_next(request, '/quality/queries/'))


class QueryCloseView(RoleRequiredMixin, View):
    action = 'raise_query'

    def post(self, request, pk):
        query = get_object_or_404(DataQuery, pk=pk)
        if request.POST.get('reopen'):
            query.status = DataQuery.Status.OPEN
            query.closed_by = query.closed_at = None
            messages.success(request, 'Query reopened.')
        else:
            query.status = DataQuery.Status.CLOSED
            query.closed_by, query.closed_at = request.user, timezone.now()
            messages.success(request, 'Query closed.')
        query.save()
        return redirect(_safe_next(request, '/quality/queries/'))
