from django.conf import settings

from .roles import ACTIONS, user_can


class _Perms:
    def __init__(self, user):
        self.user = user

    def __getitem__(self, action):
        return user_can(self.user, action)

    def __contains__(self, action):
        return action in ACTIONS


def site(request):
    from crf import spec
    user = getattr(request, 'user', None)
    return {'SITE_NAME': settings.SITE_NAME, 'SITE_SUBTITLE': settings.SITE_SUBTITLE, 'can': _Perms(user) if user is not None else {},
            'crf_forms': [s for s in spec.SECTIONS if s.fields], 'qcounts': _QualityCounts(user)}


class _QualityCounts:
    """Side-menu badge numbers, computed only when a page with the Data quality menu reads them."""

    def __init__(self, user):
        self.user, self._data = user, None

    def __getitem__(self, key):
        if self._data is None:
            from quality.counts import sidebar_counts
            self._data = sidebar_counts() if self.user is not None and user_can(self.user, 'view_quality') else {}
        return self._data.get(key, 0)
