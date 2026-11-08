from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .roles import user_can


class RoleRequiredMixin(LoginRequiredMixin):
    """Allow the view when the user may do `action` (a string, or a tuple meaning any of them)."""

    action = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        actions = (self.action,) if isinstance(self.action, str) else self.action
        if not any(user_can(request.user, a) for a in actions):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
