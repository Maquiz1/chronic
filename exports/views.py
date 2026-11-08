from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts.mixins import RoleRequiredMixin
from accounts.roles import user_can
from crf import exports as ex
from crf import spec
from crf.dictionary import archived_versions, build_workbook, codebook_pdf, dictionary_filename
from crf.models import SECTION_MODELS, Participant

from .models import ExportJob
from .tasks import run_export

EXPORT_ACTIONS = ('export_deidentified', 'export_identifiable')
CONTENT_TYPES = {'csv': 'text/csv; charset=utf-8',
                 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


class ExportPageView(RoleRequiredMixin, TemplateView):
    """One row per section with its record count; codebooks for everyone with data access, data for export roles."""

    action = 'view_data'
    template_name = 'exports/export_page.html'

    def get_context_data(self, **kwargs):
        total = Participant.objects.count()
        rows = []
        for code, label in ex.datasets():
            model = SECTION_MODELS.get(code)
            count = model.objects.filter(is_deleted=False, participant__is_deleted=False).count() if model else total
            rows.append({'key': code, 'label': label, 'count': count,
                         'calculated': model is None})
        user = self.request.user
        recent = ExportJob.objects.filter(user=user, status=ExportJob.Status.DONE,
                                          created_at__gte=timezone.now() - timedelta(hours=settings.EXPORT_FILE_HOURS))
        return {**super().get_context_data(**kwargs), 'rows': rows, 'total': total, 'modes': ex.MODES,
                'formats': ex.FORMATS, 'can_export': any(user_can(user, a) for a in EXPORT_ACTIONS),
                'recent': recent.defer('content')[:10], 'hours': settings.EXPORT_FILE_HOURS,
                'version': spec.VERSION, 'archived': [v for v, _p in archived_versions()]}


class StartExportView(RoleRequiredMixin, View):
    action = EXPORT_ACTIONS

    def post(self, request):
        dataset = request.POST.get('dataset', '')
        mode = request.POST.get('mode', 'codes')
        fmt = request.POST.get('format', 'xlsx')
        identifiable = request.POST.get('identifiable') == '1'
        if (dataset not in ('all', 'combined') and dataset not in spec.SECTION_BY_CODE) \
                or mode not in ex.MODES or fmt not in ex.FORMATS:
            return JsonResponse({'error': 'Unknown export.'}, status=400)
        if identifiable and not user_can(request.user, 'export_identifiable'):
            raise PermissionDenied
        if dataset == 'all':
            fmt = 'xlsx'  # one sheet per section
        job = ExportJob.objects.create(user=request.user, dataset=dataset, mode=mode, fmt=fmt, identifiable=identifiable)
        run_export.delay(job.pk)
        return JsonResponse({'job': job.pk, 'status_url': reverse('exports:status', args=[job.pk])})


def _own_job(request, pk):
    job = get_object_or_404(ExportJob.objects.defer('content'), pk=pk)
    if job.user_id != request.user.pk and not request.user.is_superuser:
        raise Http404('Export not found.')
    return job


class ExportStatusView(RoleRequiredMixin, View):
    action = EXPORT_ACTIONS

    def get(self, request, pk):
        job = _own_job(request, pk)
        data = {'status': job.status, 'progress': job.progress, 'rows': job.rows}
        if job.status == ExportJob.Status.DONE:
            data['file'] = reverse('exports:download', args=[job.pk])
        return JsonResponse(data)


class DownloadExportView(RoleRequiredMixin, View):
    action = EXPORT_ACTIONS

    def get(self, request, pk):
        job = _own_job(request, pk)
        if job.status != ExportJob.Status.DONE:
            raise Http404(f'Export not ready (exports are kept for {settings.EXPORT_FILE_HOURS} hours).')
        content = ExportJob.objects.values_list('content', flat=True).get(pk=job.pk)
        response = HttpResponse(bytes(content), content_type=CONTENT_TYPES[job.fmt])
        response['Content-Disposition'] = f'attachment; filename="{job.file_name}"'
        return response


class ArchivedDictionaryView(RoleRequiredMixin, View):
    """An earlier data dictionary version, exactly as it was issued."""

    action = 'view_data'

    def get(self, request, version):
        path = dict(archived_versions()).get(version)
        if path is None:
            raise Http404
        response = HttpResponse(path.read_bytes(), content_type=CONTENT_TYPES['xlsx'])
        response['Content-Disposition'] = f'attachment; filename="{path.name}"'
        return response


class CodebookView(RoleRequiredMixin, View):
    """Codebook for one section or all sections: the data dictionary workbook (Excel) or a printable PDF."""

    action = 'view_data'

    def get(self, request, key, fmt):
        section = None if key == 'all' else key.upper()
        if (section is not None and section not in spec.SECTION_BY_CODE) or fmt not in ('xlsx', 'pdf'):
            raise Http404
        if fmt == 'xlsx':
            response = HttpResponse(content_type=CONTENT_TYPES['xlsx'])
            build_workbook(section).save(response)
            name = dictionary_filename(section)
        else:
            response = HttpResponse(codebook_pdf(section), content_type='application/pdf')
            name = dictionary_filename(section).replace('Data_Dictionary', 'Codebook').replace('.xlsx', '.pdf')
        response['Content-Disposition'] = f'attachment; filename="{name}"'
        return response
