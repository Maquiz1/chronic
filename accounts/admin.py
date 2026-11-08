from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import User


@admin.register(User)
class UserAdmin(SimpleHistoryAdmin, BaseUserAdmin):
    ordering = ['email']
    list_display = ['email', 'first_name', 'last_name', 'role_labels', 'is_active', 'email_verified', 'date_joined']
    list_filter = ['groups', 'is_active', 'email_verified', 'is_superuser']
    filter_horizontal = ['groups']
    search_fields = ['email', 'first_name', 'last_name']
    fieldsets = [
        (None, {'fields': ['email', 'password']}),
        ('Person', {'fields': ['first_name', 'last_name', 'phone', 'institution', 'position']}),
        ('Access', {'fields': ['groups', 'is_active', 'email_verified', 'is_staff', 'is_superuser', 'approved_at',
                               'approved_by']}),
        ('Dates', {'fields': ['last_login', 'date_joined']}),
    ]
    add_fieldsets = [(None, {'classes': ['wide'], 'fields': ['email', 'first_name', 'last_name', 'groups',
                                                             'password1', 'password2']})]
    readonly_fields = ['approved_at', 'approved_by', 'last_login', 'date_joined']
