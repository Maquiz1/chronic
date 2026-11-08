from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from simple_history.models import HistoricalRecords

from .roles import ROLE_LABELS, user_can, user_roles


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError('An email address is required.')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, is_active=True, email_verified=True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Account identified by email. A role is given by an Admin or Data Manager after registration."""

    username = None
    email = models.EmailField('email address', unique=True)
    phone = models.CharField(max_length=30, blank=True)
    institution = models.CharField('institution / department', max_length=150, blank=True)
    position = models.CharField('position', max_length=100, blank=True, help_text='E.g. Resident, Research assistant.')
    email_verified = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    history = HistoricalRecords(excluded_fields=['password', 'last_login'])

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    class Meta:
        ordering = ['first_name', 'last_name', 'email']

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or '').strip().lower()
        super().save(*args, **kwargs)

    @property
    def role_codes(self):
        return user_roles(self)

    @property
    def role_labels(self):
        """Roles as text, in the standard order, e.g. 'Data Manager, Research Scientist / Investigator'."""
        labels = [label for code, label in ROLE_LABELS.items() if code in self.role_codes]
        if self.is_superuser:
            labels.append('Superuser')
        return ', '.join(labels)

    @property
    def is_approved(self):
        return self.is_superuser or bool(self.role_codes)

    @property
    def status_label(self):
        if not self.is_active and not self.email_verified:
            return 'Email not confirmed'
        if not self.is_active:
            return 'Deactivated'
        if not self.is_approved:
            return 'Waiting for approval'
        return 'Active'

    def can(self, action):
        return user_can(self, action)
