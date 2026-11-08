from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from accounts.mixins import RoleRequiredMixin
from accounts.roles import user_can
from quality import checks
from quality.models import DataQuery

from . import derived, spec
from .forms import ParticipantForm, QueryForm, section_form_class
from .models import SECTION_MODELS, SECTION_RELATED, Participant

ENTRY_CODES = [s.code for s in spec.SECTIONS if s.fields]


def participants_with_sections():
    return Participant.objects.select_related('interviewer', *SECTION_RELATED)


class DashboardView(RoleRequiredMixin, TemplateView):
    action = 'view_data'
    template_name = 'crf/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        participants = list(participants_with_sections())
        statuses = [checks.record_status(p.values()) for p in participants]
        ctx['total'] = len(participants)
        ctx['complete'] = sum(1 for s in statuses if s['complete'])
        ctx['locked'] = sum(1 for p in participants if p.locked)
        ctx['avg_pct'] = round(sum(s['pct'] for s in statuses) / len(statuses)) if statuses else 0
        ctx['this_week'] = sum(1 for p in participants if (timezone.localdate() - p.interview_date).days < 7)
        per_section = []
        for code in ENTRY_CODES:
            rows = [next(x for x in s['sections'] if x['code'] == code) for s in statuses]
            done = sum(r['answered'] + r['not_done'] for r in rows)
            expected = sum(r['expected'] for r in rows)
            per_section.append({'code': code, 'title': spec.SECTION_BY_CODE[code].title,
                                'complete': sum(1 for r in rows if r['state'] == 'complete'),
                                'missing': sum(len(r['missing']) for r in rows),
                                'pct': round(100 * done / expected) if expected else 0})
        ctx['per_section'] = per_section
        ctx['open_queries'] = DataQuery.objects.filter(status=DataQuery.Status.OPEN).count()
        ctx['answered_queries'] = DataQuery.objects.filter(status=DataQuery.Status.ANSWERED).count()
        ctx['recent'] = list(zip(participants[:8], statuses[:8]))
        return ctx


class ParticipantListView(RoleRequiredMixin, ListView):
    action = 'view_data'
    template_name = 'crf/participant_list.html'
    paginate_by = 50

    def get_queryset(self):
        qs = participants_with_sections()
        q = self.request.GET.get('q', '').strip()
        if q:
            cond = Q(study_id__icontains=q)
            if user_can(self.request.user, 'view_identity'):
                cond |= Q(phone_number__icontains=q) | Q(hospital_id__icontains=q)
            qs = qs.filter(cond)
        if self.request.GET.get('locked') == '1':
            qs = qs.filter(locked=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = [(p, checks.record_status(p.values())) for p in ctx['object_list']]
        status = self.request.GET.get('status')
        if status == 'complete':
            rows = [r for r in rows if r[1]['complete']]
        elif status == 'incomplete':
            rows = [r for r in rows if not r[1]['complete']]
        ctx['rows'] = rows
        ctx['entry_codes'] = ENTRY_CODES
        return ctx


class ParticipantCreateView(RoleRequiredMixin, CreateView):
    action = 'enter_data'
    form_class = ParticipantForm
    template_name = 'crf/participant_form.html'

    def get_initial(self):
        return {'interview_date': timezone.localdate()}

    def form_valid(self, form):
        form.instance.interviewer = self.request.user
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Participant {self.object.study_id} registered. Write this Study ID on the '
                                       f'paper questionnaire.')
        return response

    def get_success_url(self):
        return reverse('crf:section', args=[self.object.pk, ENTRY_CODES[0]])


class ParticipantMixin:
    def get_participant(self):
        if not hasattr(self, '_participant'):
            self._participant = get_object_or_404(participants_with_sections(), pk=self.kwargs['pk'])
        return self._participant

    def check_editable(self, participant):
        if participant.locked:
            messages.error(self.request, f'{participant} is verified and locked. A Data Manager must unlock it first.')
            return False
        return True


class ParticipantDetailView(RoleRequiredMixin, ParticipantMixin, DetailView):
    action = 'view_data'
    template_name = 'crf/participant_detail.html'
    context_object_name = 'participant'

    def get_object(self, queryset=None):
        return self.get_participant()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        p = self.object
        values = p.values()
        ctx['status'] = checks.record_status(values)
        ctx['scores'] = derived.compute_all(values)
        ctx['issues'] = checks.all_issues(values)
        ctx['queries'] = p.queries.select_related('raised_by', 'answered_by')
        labs = []
        for f in spec.SECTION_BY_CODE['G'].fields:
            if f.type in ('integer', 'decimal'):
                unit, _h, _c, ref = spec.limits(f, values)
                labs.append({'f': f, 'value': values.get(f.name), 'unit': unit or f.unit, 'ref': ref,
                             'flag': checks.reference_flag(f, values),
                             'nd': f.name in (values.get('_nd_G') or [])})
        ctx['labs'] = labs
        ctx['query_form'] = QueryForm()
        return ctx


class ParticipantEditView(RoleRequiredMixin, ParticipantMixin, UpdateView):
    action = 'enter_data'
    form_class = ParticipantForm
    template_name = 'crf/participant_form.html'

    def get_object(self, queryset=None):
        return self.get_participant()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and user_can(request.user, 'enter_data') \
                and not self.check_editable(self.get_participant()):
            return redirect('crf:detail', pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'show_identity': user_can(self.request.user, 'view_identity')}

    def form_valid(self, form):
        messages.success(self.request, 'Saved.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('crf:detail', args=[self.object.pk])


class SectionEditView(RoleRequiredMixin, ParticipantMixin, TemplateView):
    """Open one CRF section of a participant. People who enter data fill and save it (gaps are normal: missing items
    show in red and on the quality pages); everyone else, and anyone on a locked record, sees it read-only."""

    action = 'view_data'
    template_name = 'crf/section_form.html'

    def setup_section(self):
        code = self.kwargs['code'].upper()
        if code not in SECTION_MODELS:
            raise Http404
        participant = self.get_participant()
        self.values = participant.values()  # before a new (unsaved) section row is attached to the participant
        self.deleted_row = None
        row = participant.section(code, include_deleted=True)
        if row is not None and row.is_deleted:
            self.deleted_row, row = row, None
        instance = row or SECTION_MODELS[code](participant=participant)
        return code, participant, instance

    def editable(self, participant):
        return user_can(self.request.user, 'enter_data') and not participant.locked and self.deleted_row is None

    def build_form(self, code, participant, instance, data=None, readonly=False):
        form = section_form_class(code)(data, instance=instance, other_values=self.values)
        if readonly:
            for field in form.fields.values():
                field.disabled = True
        return form

    def get(self, request, *args, **kwargs):
        code, participant, instance = self.setup_section()
        readonly = not self.editable(participant)
        form = self.build_form(code, participant, instance, readonly=readonly)
        return self.render_to_response(self.context(code, participant, form, readonly))

    def post(self, request, *args, **kwargs):
        code, participant, instance = self.setup_section()
        if not user_can(request.user, 'enter_data'):
            raise PermissionDenied
        if self.deleted_row is not None:
            messages.error(request, f'Section {code} of {participant} was deleted. An Admin can restore it.')
            return redirect('crf:section', pk=participant.pk, code=code)
        if not self.check_editable(participant):
            return redirect('crf:section', pk=participant.pk, code=code)
        form = self.build_form(code, participant, instance, request.POST)
        if not form.is_valid():
            messages.error(request, 'Not saved: correct the fields marked in red.')
            return self.render_to_response(self.context(code, participant, form, False))
        obj = form.save(commit=False)
        obj.updated_by = request.user
        obj.save()
        participant.save(update_fields=['updated_at'])
        status = checks.section_status(code, Participant.objects.get(pk=participant.pk).values())
        if status['missing']:
            messages.warning(request, f'Section {code} saved. {len(status["missing"])} item(s) still missing (red): '
                                      'you can come back and complete them later.')
        else:
            messages.success(request, f'Section {code} saved and complete.')
        next_code = self.next_code(code)
        if 'save_next' in request.POST and next_code:
            return redirect('crf:section', pk=participant.pk, code=next_code)
        if 'save_close' in request.POST:
            return redirect(request.POST.get('back') if _safe(request.POST.get('back')) else
                            reverse('crf:detail', args=[participant.pk]))
        return redirect(reverse('crf:section', args=[participant.pk, code]) +
                        (f'?back={request.POST["back"]}' if _safe(request.POST.get('back')) else ''))

    @staticmethod
    def next_code(code):
        i = ENTRY_CODES.index(code)
        return ENTRY_CODES[i + 1] if i + 1 < len(ENTRY_CODES) else None

    def context(self, code, participant, form, readonly):
        values = self.values
        back = self.request.GET.get('back') or self.request.POST.get('back')
        return {'participant': participant, 'section': spec.SECTION_BY_CODE[code], 'form': form,
                'rows': form.rows(), 'next_code': self.next_code(code), 'entry_codes': ENTRY_CODES,
                'scores': derived.compute_all(values) if code in ('F', 'G', 'K') else None,
                'status': checks.section_status(code, values), 'readonly': readonly,
                'deleted_row': self.deleted_row, 'back': back if _safe(back) else '',
                'can_edit_role': user_can(self.request.user, 'enter_data')}


def _safe(url):
    return bool(url) and url.startswith('/') and not url.startswith('//')


class FormListView(RoleRequiredMixin, TemplateView):
    """One CRF form (section): every participant with its status, to enter, update, view or delete."""

    action = 'view_data'
    template_name = 'crf/form_list.html'

    def get_context_data(self, **kwargs):
        code = self.kwargs['code'].upper()
        if code not in SECTION_MODELS:
            raise Http404
        section = spec.SECTION_BY_CODE[code]
        qs = participants_with_sections().order_by('-interview_date', '-study_id')
        q = self.request.GET.get('q', '').strip()
        if q:
            cond = Q(study_id__icontains=q)
            if user_can(self.request.user, 'view_identity'):
                cond |= Q(hospital_id__icontains=q)
            qs = qs.filter(cond)
        show = self.request.GET.get('show', 'all')
        rows = []
        for p in qs:
            status = checks.section_status(code, p.values())
            if show != 'all' and status['state'] != show:
                continue
            rows.append({'p': p, 'status': status, 'row': p.section(code)})
        return {**super().get_context_data(**kwargs), 'section': section, 'rows': rows, 'show': show,
                'entry_codes': ENTRY_CODES}


class SectionDeleteView(RoleRequiredMixin, ParticipantMixin, View):
    """Soft-delete one participant's form: it counts as not entered until an Admin restores it."""

    action = 'delete_record'

    def post(self, request, pk, code):
        code = code.upper()
        participant = self.get_participant()
        row = participant.section(code)
        if row is None:
            raise Http404
        if participant.locked:
            messages.error(request, f'{participant} is locked. Unlock it before deleting a section.')
        else:
            reason = request.POST.get('reason', '').strip()[:255]
            if not reason:
                messages.error(request, 'Give a reason for deleting the section.')
            else:
                row.soft_delete(request.user, reason)
                messages.success(request, f'Section {code} of {participant} deleted. An Admin can restore it from '
                                          f'Deleted records.')
        back = request.POST.get('back')
        return redirect(back if _safe(back) else reverse('crf:form_list', args=[code]))


class DeletedRecordsView(RoleRequiredMixin, TemplateView):
    action = 'restore_record'
    template_name = 'crf/deleted_records.html'

    def get_context_data(self, **kwargs):
        participants = Participant.all_objects.filter(is_deleted=True).select_related('deleted_by')
        sections = []
        for code, model in SECTION_MODELS.items():
            for row in model.objects.filter(is_deleted=True, participant__is_deleted=False).select_related(
                    'participant', 'deleted_by'):
                sections.append({'code': code, 'title': spec.SECTION_BY_CODE[code].title, 'row': row})
        sections.sort(key=lambda x: x['row'].deleted_at, reverse=True)
        return {**super().get_context_data(**kwargs), 'participants': participants, 'sections': sections}


class RestoreView(RoleRequiredMixin, View):
    action = 'restore_record'

    def post(self, request, kind, pk, code=None):
        if kind == 'participant':
            participant = get_object_or_404(Participant.all_objects, pk=pk, is_deleted=True)
            participant.restore()
            messages.success(request, f'{participant} restored with all its sections.')
            return redirect('crf:detail', pk=participant.pk)
        code = (code or '').upper()
        if code not in SECTION_MODELS:
            raise Http404
        row = get_object_or_404(SECTION_MODELS[code], participant_id=pk, is_deleted=True)
        row.restore()
        messages.success(request, f'Section {code} of {row.participant} restored.')
        return redirect('crf:section', pk=pk, code=code)


class LockView(RoleRequiredMixin, ParticipantMixin, View):
    action = 'lock_record'

    def post(self, request, pk):
        participant = self.get_participant()
        if request.POST.get('unlock'):
            participant.unlock()
            messages.success(request, f'{participant} unlocked for corrections.')
        else:
            open_queries = participant.queries.exclude(status=DataQuery.Status.CLOSED).count()
            if open_queries and not request.POST.get('force'):
                messages.error(request, f'{participant} has {open_queries} query(ies) not closed. Close them first.')
            else:
                participant.lock(request.user)
                messages.success(request, f'{participant} verified and locked.')
        return redirect('crf:detail', pk=pk)


class ParticipantDeleteView(RoleRequiredMixin, ParticipantMixin, TemplateView):
    """Soft delete: the participant disappears from lists, exports and reports, and an Admin can restore it."""

    action = 'delete_record'
    template_name = 'crf/participant_confirm_delete.html'

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'participant': self.get_participant()}

    def post(self, request, pk):
        participant = self.get_participant()
        reason = request.POST.get('reason', '').strip()[:255]
        if request.POST.get('confirm_id', '').strip() != participant.study_id:
            messages.error(request, 'Type the Study ID exactly to confirm.')
            return redirect('crf:delete', pk=pk)
        if not reason:
            messages.error(request, 'Give a reason for deleting the participant.')
            return redirect('crf:delete', pk=pk)
        participant.soft_delete(request.user, reason)
        messages.success(request, f'{participant} deleted. An Admin can restore it from Deleted records.')
        return redirect('crf:list')


class HistoryView(RoleRequiredMixin, ParticipantMixin, TemplateView):
    """Who changed what and when, across the participant record and all its sections."""

    action = 'view_audit'
    template_name = 'crf/history.html'

    def get_context_data(self, **kwargs):
        participant = self.get_participant()
        show_phone = user_can(self.request.user, 'view_identity')
        entries = []
        sources = [('Header', participant.history.all())]
        for code, model in SECTION_MODELS.items():
            sources.append((code, model.history.filter(participant_id=participant.pk)))
        for label, history in sources:
            records = list(history.select_related('history_user').order_by('history_date'))
            previous = None
            for record in records:
                changes = []
                if previous is not None:
                    delta = record.diff_against(previous)
                    for change in delta.changes:
                        if change.field in ('phone_number', 'hospital_id') and not show_phone:
                            changes.append((change.field, '•••', '•••'))
                        else:
                            changes.append((change.field, change.old, change.new))
                entries.append({'section': label, 'date': record.history_date, 'user': record.history_user,
                                'type': record.get_history_type_display(), 'changes': changes})
                previous = record
        entries.sort(key=lambda e: e['date'], reverse=True)
        return {**super().get_context_data(**kwargs), 'participant': participant, 'entries': entries}
