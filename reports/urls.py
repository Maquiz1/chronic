from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.StudyProgressView.as_view(), name='study'),
    path('participants/', views.PatientProgressView.as_view(), name='patients'),
    path('pdf/', views.ReportPdfView.as_view(), name='pdf'),
    path('schedules/', views.ScheduleListView.as_view(), name='schedules'),
    path('schedules/<int:pk>/run/', views.RunTaskNowView.as_view(), name='run'),
]
