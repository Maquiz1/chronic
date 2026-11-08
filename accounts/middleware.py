from django.shortcuts import redirect
from django.urls import reverse


class ApprovedUserMiddleware:
    """Logged-in people without a role only reach their profile, password pages and logout."""

    OPEN_PREFIXES = ('/accounts/', '/static/', '/django-admin/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_approved \
                and not request.path.startswith(self.OPEN_PREFIXES):
            return redirect(reverse('accounts:pending'))
        return self.get_response(request)
