from django.urls import path

from . import views

app_name = 'crf'

urlpatterns = [
    path('', views.ParticipantListView.as_view(), name='list'),
    path('new/', views.ParticipantCreateView.as_view(), name='create'),
    path('export/', views.ExportsPageView.as_view(), name='exports'),
    path('export/download/', views.ExportView.as_view(), name='export'),
    path('dictionary/', views.DictionaryView.as_view(), name='dictionary'),
    path('<int:pk>/', views.ParticipantDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ParticipantEditView.as_view(), name='edit'),
    path('<int:pk>/section/<str:code>/', views.SectionEditView.as_view(), name='section'),
    path('<int:pk>/lock/', views.LockView.as_view(), name='lock'),
    path('<int:pk>/delete/', views.ParticipantDeleteView.as_view(), name='delete'),
    path('<int:pk>/history/', views.HistoryView.as_view(), name='history'),
]
