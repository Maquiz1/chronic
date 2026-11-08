from django.db import models


class EmailLog(models.Model):
    """Every scheduled email sent (or attempted), so an Admin can see who received what."""

    kind = models.CharField(max_length=40)
    to = models.EmailField()
    subject = models.CharField(max_length=255)
    sent = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind} -> {self.to}'
