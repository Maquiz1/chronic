"""Roles and what each one may do.

A person can hold several roles (e.g. Data Manager and Research Scientist / Investigator); they may do anything any
of their roles allows. Roles are stored as Django groups named after the role labels below.

Who can give which roles:
  Data Manager  -> Data Clerk, Research Scientist / Investigator
  Admin         -> the above and Data Manager
  Superuser     -> all roles, including Admin
People can also register themselves with their email; they get no role until someone gives them one.

Only Data Clerks, Data Managers and Admins see hospital IDs and phone numbers.
"""

DATA_CLERK = 'data_clerk'
INVESTIGATOR = 'investigator'
DATA_MANAGER = 'data_manager'
ADMIN = 'admin'

ROLE_CHOICES = [
    (DATA_CLERK, 'Data Clerk'),
    (INVESTIGATOR, 'Research Scientist / Investigator'),
    (DATA_MANAGER, 'Data Manager'),
    (ADMIN, 'Admin'),
]
ROLE_LABELS = dict(ROLE_CHOICES)
# Group name -> role code. Group names are the labels, so they read well in Django admin.
GROUP_TO_ROLE = {label: code for code, label in ROLE_CHOICES}

# Action -> description, shown on the roles page.
ACTIONS = {
    'view_data': 'View participant records, reports and the data dictionary',
    'view_identity': 'See hospital IDs and phone numbers',
    'enter_data': 'Register participants and enter or update CRF sections',
    'view_quality': 'See data quality: missing fields, pending results, checks',
    'answer_query': 'Answer data queries',
    'raise_query': 'Raise and close data queries',
    'lock_record': 'Lock (verify) and unlock records',
    'delete_record': 'Delete a participant record',
    'export_deidentified': 'Export data without hospital IDs or phone numbers',
    'export_identifiable': 'Export data with hospital IDs and phone numbers',
    'view_audit': 'See the change history (audit trail)',
    'approve_users': 'Create and approve Data Clerks and Research Scientists / Investigators',
    'manage_users': 'Also create and manage Data Managers (Admins are created by a superuser)',
    'manage_tasks': 'See scheduled tasks and sent emails, run a task now',
}

PERMISSIONS = {
    DATA_CLERK: {'view_data', 'view_identity', 'enter_data', 'view_quality', 'answer_query'},
    INVESTIGATOR: {'view_data', 'view_quality', 'export_deidentified'},
    DATA_MANAGER: {'view_data', 'view_identity', 'enter_data', 'view_quality', 'answer_query', 'raise_query',
                   'lock_record', 'delete_record', 'export_deidentified', 'export_identifiable', 'view_audit',
                   'approve_users'},
    ADMIN: set(ACTIONS),
}


def user_roles(user):
    """Set of role codes. Cached on the user object for the request."""
    if not getattr(user, 'is_authenticated', False):
        return set()
    cached = getattr(user, '_role_codes', None)
    if cached is None:
        names = user.groups.values_list('name', flat=True) if user.pk else []
        cached = {GROUP_TO_ROLE[n] for n in names if n in GROUP_TO_ROLE}
        user._role_codes = cached
    return cached


def user_can(user, action):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return any(action in PERMISSIONS[r] for r in user_roles(user))


def assignable_roles(actor):
    """Roles this person may give, as [(code, label)]."""
    if actor.is_superuser:
        allowed = {DATA_CLERK, INVESTIGATOR, DATA_MANAGER, ADMIN}
    elif ADMIN in user_roles(actor):
        allowed = {DATA_CLERK, INVESTIGATOR, DATA_MANAGER}
    elif DATA_MANAGER in user_roles(actor):
        allowed = {DATA_CLERK, INVESTIGATOR}
    else:
        allowed = set()
    return [(code, label) for code, label in ROLE_CHOICES if code in allowed]


def can_manage(actor, target):
    """Whether `actor` may edit `target`: only accounts whose roles are all ones the actor may give."""
    if not actor.is_authenticated or not actor.is_active:
        return False
    if actor.is_superuser:
        return True
    if target.is_superuser or target.pk == actor.pk:
        return False
    allowed = {code for code, _ in assignable_roles(actor)}
    return bool(allowed) and user_roles(target) <= allowed


def set_roles(user, codes):
    """Replace the user's roles with `codes`."""
    from django.contrib.auth.models import Group
    groups = [Group.objects.get_or_create(name=ROLE_LABELS[c])[0] for c in codes]
    others = user.groups.exclude(name__in=GROUP_TO_ROLE)
    user.groups.set(list(others) + groups)
    user._role_codes = set(codes)


def users_with_roles(queryset, codes):
    """Filter a User queryset to people holding any of the given roles."""
    return queryset.filter(groups__name__in=[ROLE_LABELS[c] for c in codes]).distinct()
