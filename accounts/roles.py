"""Roles and what each one may do.

A person registers with their email, confirms it, and then waits until an Admin (or a Data Manager, for the
Data Clerk and Investigator roles) gives them a role. Without a role they can only see their profile.

Only Data Clerks, Data Managers and Admins see the patient phone number. Investigators work with study IDs only.
"""

DATA_CLERK = 'data_clerk'
INVESTIGATOR = 'investigator'
DATA_MANAGER = 'data_manager'
ADMIN = 'admin'

ROLE_CHOICES = [
    (DATA_CLERK, 'Data Clerk'),
    (INVESTIGATOR, 'Investigator'),
    (DATA_MANAGER, 'Data Manager'),
    (ADMIN, 'Admin'),
]

# Action -> description, shown on the roles page.
ACTIONS = {
    'view_data': 'View participant records',
    'view_identity': 'See the patient phone number',
    'enter_data': 'Register participants and enter or update CRF sections',
    'view_quality': 'See data quality: missing fields, pending results, checks',
    'answer_query': 'Answer data queries',
    'raise_query': 'Raise and close data queries',
    'lock_record': 'Lock (verify) and unlock records',
    'delete_record': 'Delete a participant record',
    'export_deidentified': 'Export data without phone numbers',
    'export_identifiable': 'Export data with phone numbers',
    'view_audit': 'See the change history (audit trail)',
    'approve_users': 'Approve new accounts as Data Clerk or Investigator',
    'manage_users': 'Manage all accounts and roles, including Admins and Data Managers',
}

PERMISSIONS = {
    DATA_CLERK: {'view_data', 'view_identity', 'enter_data', 'view_quality', 'answer_query'},
    INVESTIGATOR: {'view_data', 'view_quality', 'export_deidentified'},
    DATA_MANAGER: {'view_data', 'view_identity', 'enter_data', 'view_quality', 'answer_query', 'raise_query',
                   'lock_record', 'delete_record', 'export_deidentified', 'export_identifiable', 'view_audit',
                   'approve_users'},
    ADMIN: set(ACTIONS),
}

# Roles a person with the given action may hand out.
ASSIGNABLE = {
    'approve_users': {DATA_CLERK, INVESTIGATOR},
    'manage_users': {DATA_CLERK, INVESTIGATOR, DATA_MANAGER, ADMIN},
}


def user_can(user, action):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return action in PERMISSIONS.get(user.role, set())


def assignable_roles(user):
    roles = set()
    for action, allowed in ASSIGNABLE.items():
        if user_can(user, action):
            roles |= allowed
    return [(code, label) for code, label in ROLE_CHOICES if code in roles]
