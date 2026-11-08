"""Numbers for the badges next to the Data quality links in the side menu.

Computed in one pass over all records, cached (Redis in production) and cleared whenever a record, a section or a
query is saved or deleted, so the badges are current without recomputing on every page.
"""
import logging

from django.core.cache import cache

CACHE_KEY = 'quality:sidebar-counts'
CACHE_SECONDS = 300
log = logging.getLogger(__name__)


def compute():
    from crf.views import participants_with_sections
    from . import checks
    from .models import DataQuery

    open_q = set(DataQuery.objects.exclude(status=DataQuery.Status.CLOSED).values_list('participant_id', flat=True))
    counts = {'to_review': 0, 'pending': 0, 'errors': 0, 'warnings': 0,
              'open_queries': DataQuery.objects.filter(status=DataQuery.Status.OPEN).count(),
              'answered_queries': DataQuery.objects.filter(status=DataQuery.Status.ANSWERED).count()}
    for p in participants_with_sections():
        v = p.values()
        status, issues = checks.record_status(v), checks.all_issues(v)
        # Completeness page (default view): records not complete, or with check results or open queries
        if not status['complete'] or issues or p.pk in open_q:
            counts['to_review'] += 1
        # Pending results page (default: Section G): unlocked records still waiting for a result
        if not p.locked:
            g = checks.section_status('G', v)
            if g['missing'] or g['state'] == 'not_started':
                counts['pending'] += 1
        counts['errors'] += sum(1 for i in issues if i.level == checks.ERROR)
        counts['warnings'] += sum(1 for i in issues if i.level == checks.WARNING)
    return counts


def sidebar_counts():
    try:
        counts = cache.get(CACHE_KEY)
    except Exception:  # cache unreachable: still show the numbers
        log.warning('cache unavailable for quality counts', exc_info=True)
        return compute()
    if counts is None:
        counts = compute()
        try:
            cache.set(CACHE_KEY, counts, CACHE_SECONDS)
        except Exception:
            pass
    return counts


def clear(**_kwargs):
    try:
        cache.delete(CACHE_KEY)
    except Exception:
        pass
