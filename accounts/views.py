from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import FormView, ListView, TemplateView, UpdateView

from .emails import notify_approvers, send_approved_email, send_verification_email
from .forms import EmailLoginForm, ProfileForm, RegistrationForm, StyledPasswordChangeForm, UserAdminForm
from .mixins import RoleRequiredMixin
from .models import User
from .roles import ACTIONS, PERMISSIONS, ROLE_CHOICES, assignable_roles, user_can


class LoginView(auth_views.LoginView):
    form_class = EmailLoginForm
    template_name = 'registration/login.html'
    redirect_authenticated_user = True


class RegisterView(FormView):
    template_name = 'registration/register.html'
    form_class = RegistrationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        send_verification_email(self.request, user)
        return render(self.request, 'registration/register_done.html', {'email': user.email})


class ResendVerificationView(View):
    def post(self, request):
        email = request.POST.get('email', '').strip().lower()
        user = User.objects.filter(email=email, email_verified=False).first()
        if user:
            send_verification_email(request, user)
        # Same answer whether the account exists or not, so emails cannot be probed.
        messages.info(request, 'If that email is registered and not yet confirmed, a new link has been sent.')
        return redirect('login')


class VerifyEmailView(View):
    def get(self, request, uidb64, token):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return render(request, 'registration/verify_failed.html', status=400)
        if not user.email_verified:
            user.email_verified = True
            user.is_active = True
            user.save(update_fields=['email_verified', 'is_active'])
            notify_approvers(request, user)
        messages.success(request, 'Your email is confirmed. You can log in now. An administrator will give you a '
                                  'role before you can see study data.')
        return redirect('login')


class PendingApprovalView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/pending.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_approved:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)


class ProfileView(LoginRequiredMixin, UpdateView):
    template_name = 'accounts/profile.html'
    form_class = ProfileForm
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profile saved.')
        return super().form_valid(form)


class PasswordChangeView(auth_views.PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been changed.')
        return super().form_valid(form)


# --- User management ------------------------------------------------------------------------------------------

def _can_manage(actor, target):
    """Admins manage everyone. Data Managers only accounts without a role, Data Clerks and Investigators."""
    if user_can(actor, 'manage_users'):
        return True
    if user_can(actor, 'approve_users'):
        return not target.is_superuser and target.role in ('', 'data_clerk', 'investigator') and target != actor
    return False


class UserListView(RoleRequiredMixin, ListView):
    action = ('approve_users', 'manage_users')
    template_name = 'accounts/user_list.html'
    paginate_by = 50

    def get_queryset(self):
        qs = User.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        status = self.request.GET.get('status')
        if status == 'pending':
            qs = qs.filter(is_active=True, role='', is_superuser=False)
        elif status == 'unconfirmed':
            qs = qs.filter(email_verified=False)
        return qs.order_by('-date_joined')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_count'] = User.objects.filter(is_active=True, role='', is_superuser=False).count()
        ctx['manageable'] = {u.pk for u in ctx['object_list'] if _can_manage(self.request.user, u)}
        return ctx


class UserEditView(RoleRequiredMixin, UpdateView):
    action = ('approve_users', 'manage_users')
    model = User
    form_class = UserAdminForm
    template_name = 'accounts/user_edit.html'
    success_url = reverse_lazy('accounts:users')

    def get_object(self, queryset=None):
        target = get_object_or_404(User, pk=self.kwargs['pk'])
        if not _can_manage(self.request.user, target):
            raise PermissionDenied
        return target

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'allowed_roles': assignable_roles(self.request.user)}

    def form_valid(self, form):
        user = form.instance
        newly_approved = form.cleaned_data['role'] and not form.initial.get('role')
        if user == self.request.user and not form.cleaned_data['is_active']:
            form.add_error('is_active', 'You cannot deactivate your own account.')
            return self.form_invalid(form)
        if newly_approved:
            user.approved_at = timezone.now()
            user.approved_by = self.request.user
        response = super().form_valid(form)
        if newly_approved and user.is_active:
            send_approved_email(self.request, user)
            messages.success(self.request, f'{user} is approved as {user.get_role_display()} and has been emailed.')
        else:
            messages.success(self.request, f'{user} saved.')
        return response


class ResendUserVerificationView(RoleRequiredMixin, View):
    action = ('approve_users', 'manage_users')

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, email_verified=False)
        send_verification_email(request, user)
        messages.success(request, f'A new confirmation link was sent to {user.email}.')
        return redirect(reverse('accounts:users'))


class RolesView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/roles.html'

    def get_context_data(self, **kwargs):
        rows = [(label, [code in PERMISSIONS[role] for role, _ in ROLE_CHOICES]) for code, label in ACTIONS.items()]
        return {**super().get_context_data(**kwargs), 'roles': ROLE_CHOICES, 'rows': rows}
