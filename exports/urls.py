from django.urls import path

from . import views

app_name = 'exports'

urlpatterns = [
    path('', views.ExportPageView.as_view(), name='page'),
    path('start/', views.StartExportView.as_view(), name='start'),
    path('<int:pk>/status/', views.ExportStatusView.as_view(), name='status'),
    path('<int:pk>/download/', views.DownloadExportView.as_view(), name='download'),
    path('codebook/<str:key>/<str:fmt>/', views.CodebookView.as_view(), name='codebook'),
]
