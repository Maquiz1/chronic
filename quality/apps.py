from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


def _clear_counts(sender, **kwargs):
    if sender._meta.app_label in ('crf', 'quality') and not sender.__name__.startswith('Historical'):
        from .counts import clear
        clear()


class QualityConfig(AppConfig):
    name = 'quality'
    verbose_name = 'Data quality'

    def ready(self):
        post_save.connect(_clear_counts, dispatch_uid='quality-counts-save')
        post_delete.connect(_clear_counts, dispatch_uid='quality-counts-delete')
