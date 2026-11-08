from django.contrib import admin

from .models import ExportJob


@admin.register(ExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'dataset', 'mode', 'fmt', 'identifiable', 'status', 'rows']
    list_filter = ['status', 'identifiable', 'dataset']
    readonly_fields = [f.name for f in ExportJob._meta.fields if f.name != 'content']
    exclude = ['content']

    def has_add_permission(self, request):
        return False
