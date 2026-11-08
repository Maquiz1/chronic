from django.urls import path

from . import views

app_name = 'crf'

urlpatterns = [
    path('', views.ParticipantListView.as_view(), name='list'),
    path('new/', views.ParticipantCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ParticipantDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ParticipantEditView.as_view(), name='edit'),
    path('<int:pk>/section/<str:code>/', views.SectionEditView.as_view(), name='section'),
    path('<int:pk>/lock/', views.LockView.as_view(), name='lock'),
    path('<int:pk>/delete/', views.ParticipantDeleteView.as_view(), name='delete'),
    path('<int:pk>/history/', views.HistoryView.as_view(), name='history'),
    path('<int:pk>/section/<str:code>/delete/', views.SectionDeleteView.as_view(), name='section_delete'),
    path('forms/<str:code>/', views.FormListView.as_view(), name='form_list'),
    path('deleted/', views.DeletedRecordsView.as_view(), name='deleted'),
    path('deleted/participant/<int:pk>/restore/', views.RestoreView.as_view(), {'kind': 'participant'}, name='restore_participant'),
    path('deleted/section/<int:pk>/<str:code>/restore/', views.RestoreView.as_view(), {'kind': 'section'}, name='restore_section'),
]
