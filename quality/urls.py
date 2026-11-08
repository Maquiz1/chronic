from django.urls import path

from . import views

app_name = 'quality'

urlpatterns = [
    path('', views.OverviewView.as_view(), name='overview'),
    path('pending/', views.PendingView.as_view(), name='pending'),
    path('checks/', views.IssuesView.as_view(), name='issues'),
    path('queries/', views.QueryListView.as_view(), name='queries'),
    path('queries/new/<int:pk>/', views.QueryCreateView.as_view(), name='query_create'),
    path('queries/<int:pk>/answer/', views.QueryAnswerView.as_view(), name='query_answer'),
    path('queries/<int:pk>/close/', views.QueryCloseView.as_view(), name='query_close'),
]
