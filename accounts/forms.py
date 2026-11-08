from django import forms
from django.contrib.auth.forms import (AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm,
                                       UserCreationForm)

from .models import User
from .widgets import BootstrapFormMixin


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


class RolesFieldMixin:
    """Adds a "roles" tick list limited to the roles the person editing may give."""

    def setup_roles(self, allowed_roles, current=()):
        allowed = [code for code, _ in allowed_roles]
        self.fields['roles'] = forms.MultipleChoiceField(
            choices=allowed_roles, required=False, widget=forms.CheckboxSelectMultiple,
            initial=[c for c in current if c in allowed],
            help_text='Tick one or more. With no role the person can log in but sees no study data.')
        self._allowed = set(allowed)

    def clean_roles(self):
        roles = self.cleaned_data.get('roles') or []
        if set(roles) - self._allowed:
            raise forms.ValidationError('You cannot give this role.')
        return roles


class UserAdminForm(RolesFieldMixin, BootstrapFormMixin, forms.ModelForm):
    """Used by Admins and Data Managers to approve an account, change its roles or deactivate it."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'institution', 'position', 'is_active']
        labels = {'is_active': 'Account active (can log in)'}

    def __init__(self, *args, allowed_roles=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_roles(list(allowed_roles), self.instance.role_codes)


class UserCreateForm(RolesFieldMixin, BootstrapFormMixin, forms.ModelForm):
    """An Admin or Data Manager creates an account; the person gets an email to choose their password."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'institution', 'position']

    def __init__(self, *args, allowed_roles=(), **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('first_name', 'last_name'):
            self.fields[name].required = True
        self.setup_roles(list(allowed_roles))
        self.fields['roles'].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    pass
