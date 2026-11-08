from django import forms
from django.contrib.auth.forms import (AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm,
                                       UserCreationForm)

from .models import User
from .widgets import BootstrapFormMixin
from .roles import ROLE_CHOICES


class EmailLoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}))

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Wrong email or password.',
        'inactive': 'This account is not active. If you have just registered, open the confirmation link sent to '
                    'your email first.',
    }

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'institution', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('first_name', 'last_name'):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists. Use "Forgot password" if you '
                                        'cannot log in.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False  # becomes active when the email link is opened
        if commit:
            user.save()
        return user


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'institution', 'position']


class UserAdminForm(BootstrapFormMixin, forms.ModelForm):
    """Used by Admins and Data Managers to approve an account, change its role or deactivate it."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'institution', 'position', 'role', 'is_active']
        labels = {'is_active': 'Account active (can log in)'}

    def __init__(self, *args, allowed_roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = [code for code, _ in (allowed_roles or [])]
        self.fields['role'].choices = [('', 'No role (cannot use the system)')] + [
            (code, label) for code, label in ROLE_CHOICES if code in allowed or code == self.instance.role]
        self._allowed = set(allowed)

    def clean_role(self):
        role = self.cleaned_data['role']
        if role and role != self.initial.get('role') and role not in self._allowed:
            raise forms.ValidationError('You cannot give this role.')
        return role


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass
