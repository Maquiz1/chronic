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
    user = getattr(request, 'user', None)
    return {'SITE_NAME': settings.SITE_NAME, 'can': _Perms(user) if user is not None else {}}
