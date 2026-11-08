from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('schedules/', views.ScheduleListView.as_view(), name='schedules'),
    path('schedules/<int:pk>/run/', views.RunTaskNowView.as_view(), name='run'),
]
