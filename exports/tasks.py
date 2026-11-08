import io
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from crf import exports as ex
from crf import spec
from crf.views import participants_with_sections

from .models import ExportJob

logger = logging.getLogger(__name__)


def export_file_name(job):
    tag = '_identifiable' if job.identifiable else ''
    part = {'all': 'all_sections', 'combined': 'combined'}.get(job.dataset, f'section_{job.dataset}')
    return f'dcld_{part}_{job.mode}{tag}_{timezone.localtime():%Y%m%d_%H%M}_{job.pk}.{job.fmt}'


@shared_task
def run_export(job_id):
    job = ExportJob.objects.select_related('user').get(pk=job_id)
    job.status = ExportJob.Status.RUNNING
    job.save(update_fields=['status'])
    try:
        participants = list(participants_with_sections())
        sheet_count = len(spec.SECTIONS) if job.dataset == 'all' else 1
        job.total = len(participants) * sheet_count
        job.save(update_fields=['total'])

        def progress(done):
            if done % 25 == 0 or done == job.total:
                ExportJob.objects.filter(pk=job.pk).update(done=done)

        items = ex.collect(participants)
        sheet_list = ex.sheets(items, job.dataset, job.mode, job.identifiable)
        if job.fmt == 'csv':
            text = io.StringIO()
            rows = ex.write_csv(text, sheet_list, progress)
            content = text.getvalue().encode('utf-8-sig')  # BOM so Excel opens accents correctly
        else:
            buffer = io.BytesIO()
            rows = ex.write_xlsx(buffer, sheet_list, ex.notes_rows(job.dataset, job.mode, job.identifiable), progress)
            content = buffer.getvalue()
        job.content, job.rows, job.file_name = content, rows, export_file_name(job)
        job.status, job.done, job.finished_at = ExportJob.Status.DONE, job.total, timezone.now()
        job.save()
    except Exception as exc:  # recorded so the page can say it failed
        logger.exception('Export %s failed', job_id)
        ExportJob.objects.filter(pk=job_id).update(status=ExportJob.Status.FAILED, error=str(exc)[:2000],
                                                   finished_at=timezone.now())
    delete_expired_exports()


@shared_task
def delete_expired_exports():
    cutoff = timezone.now() - timedelta(hours=settings.EXPORT_FILE_HOURS)
    deleted, _ = ExportJob.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info('Deleted %s expired export(s)', deleted)
    return deleted
