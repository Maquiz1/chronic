from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import SECTION_MODELS, Participant


@admin.register(Participant)
class ParticipantAdmin(SimpleHistoryAdmin):
    list_display = ['study_id', 'interview_date', 'admission_date', 'interviewer', 'locked', 'updated_at']
    list_filter = ['locked']
    search_fields = ['study_id']
    readonly_fields = ['study_id', 'created_by', 'created_at', 'updated_at', 'locked_by', 'locked_at']


for _model in SECTION_MODELS.values():
    admin.site.register(_model, SimpleHistoryAdmin, list_display=['participant', 'updated_by', 'updated_at'],
                        search_fields=['participant__study_id'], readonly_fields=['updated_by', 'created_at', 'updated_at'])
