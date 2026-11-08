from django.contrib import admin
from django.urls import include, path

from django.contrib.auth import views as auth_views

from accounts.views import LoginView
from crf.views import DashboardView

admin.site.site_header = 'MNH Liver Study administration'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('accounts/login/', LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/', include('accounts.urls')),
    path('records/', include('crf.urls')),
    path('quality/', include('quality.urls')),
    path('exports/', include('exports.urls')),
    path('reports/', include('reports.urls')),
    path('django-admin/', admin.site.urls),
]
