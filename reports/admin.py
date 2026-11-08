from django.contrib import admin

from .models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'kind', 'to', 'subject', 'sent']
    list_filter = ['kind', 'sent']
    search_fields = ['to', 'subject']
    readonly_fields = ['created_at', 'kind', 'to', 'subject', 'sent', 'error']

    def has_add_permission(self, request):
        return False
