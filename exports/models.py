from django.conf import settings
from django.db import models


class ExportJob(models.Model):
    """One export, run in the background by the Celery worker.

    The finished file is kept in the database (not on disk) because the worker and the web server run in separate
    containers. It can contain identifying data, so it is served only to the person who made it and deleted after
    EXPORT_FILE_HOURS.
    """

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Exporting'
        DONE = 'done', 'Ready'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    dataset = models.CharField(max_length=20)
    mode = models.CharField(max_length=10)
    fmt = models.CharField(max_length=5)
    identifiable = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    rows = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    file_name = models.CharField(max_length=200, blank=True)
    content = models.BinaryField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.file_name or f'Export {self.pk}'

    @property
    def progress(self):
        if self.status == self.Status.DONE:
            return 100
        return int(self.done * 100 / self.total) if self.total else 0
