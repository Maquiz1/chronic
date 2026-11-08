from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import DataQuery


@admin.register(DataQuery)
class DataQueryAdmin(SimpleHistoryAdmin):
    list_display = ['participant', 'section', 'field', 'status', 'raised_by', 'raised_at']
    list_filter = ['status', 'section']
    search_fields = ['participant__study_id', 'message']
