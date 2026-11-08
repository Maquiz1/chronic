import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def _absolute(path):
    return f'{settings.SITE_URL}{path}'


def _send(subject, template, context, to):
    body = render_to_string(template, {**context, 'SITE_NAME': settings.SITE_NAME, 'SITE_URL': settings.SITE_URL})
    try:
        send_mail(f'[{settings.SITE_NAME}] {subject}', body, None, to, fail_silently=False)
    except Exception:  # an email problem must not break registration; it is logged for the administrator
        logger.exception('Could not send "%s" to %s', subject, to)


def send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = _absolute(reverse('accounts:verify_email', args=[uid, token]))
    _send('Confirm your email', 'emails/verify_email.txt', {'user': user, 'link': link}, [user.email])


def notify_approvers(request, new_user):
    from .models import User
    recipients = list(User.objects.filter(is_active=True, role__in=['admin', 'data_manager'])
                      .values_list('email', flat=True))
    recipients += list(User.objects.filter(is_active=True, is_superuser=True).values_list('email', flat=True))
    recipients = sorted(set(recipients) - {new_user.email})
    if recipients:
        link = _absolute(reverse('accounts:user_edit', args=[new_user.pk]))
        _send('New account waiting for approval', 'emails/approval_needed.txt', {'new_user': new_user, 'link': link},
              recipients)


def send_approved_email(request, user):
    _send('Your account is approved', 'emails/approved.txt',
          {'user': user, 'link': _absolute(reverse('login'))}, [user.email])
