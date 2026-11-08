from django.conf import settings
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from crf.models import Participant


class DataQuery(models.Model):
    """A question about a value, raised by a Data Manager and answered by whoever enters the data."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        ANSWERED = 'answered', 'Answered'
        CLOSED = 'closed', 'Closed'

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='queries')
    section = models.CharField(max_length=10, help_text='Section code (A-L) or Header.')
    field = models.CharField(max_length=60, blank=True)
    rule = models.CharField(max_length=30, blank=True, help_text='Automatic check this query came from, if any.')
    message = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    response = models.TextField(blank=True)

    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    raised_at = models.DateTimeField(default=timezone.now)
    answered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    answered_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    closed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-raised_at']
        verbose_name_plural = 'data queries'

    def __str__(self):
        return f'{self.participant} {self.section} {self.field}: {self.message[:40]}'

    @property
    def field_label(self):
        from crf import spec
        if self.field in spec.FIELD_BY_NAME:
            _s, f = spec.FIELD_BY_NAME[self.field]
            return f'{f.qn} {f.label}'
        return self.field
