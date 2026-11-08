from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import StyledPasswordResetForm, StyledSetPasswordForm

app_name = 'accounts'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify/<uidb64>/<token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    path('verify/resend/', views.ResendVerificationView.as_view(), name='resend_verification'),
    path('pending/', views.PendingApprovalView.as_view(), name='pending'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/password/', views.PasswordChangeView.as_view(), name='password_change'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        form_class=StyledPasswordResetForm,
        extra_email_context={'SITE_NAME': settings.SITE_NAME, 'STUDY_TAGLINE': settings.STUDY_TAGLINE},
        email_template_name='emails/password_reset.txt', subject_template_name='emails/password_reset_subject.txt',
        success_url=reverse_lazy('accounts:password_reset_done')), name='password_reset'),
    path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        form_class=StyledSetPasswordForm,
        success_url=reverse_lazy('accounts:password_reset_complete')), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('users/', views.UserListView.as_view(), name='users'),
    path('users/new/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/resend/', views.ResendUserVerificationView.as_view(), name='user_resend'),
    path('users/<int:pk>/activation/', views.UserActivationView.as_view(), name='user_activation'),
    path('roles/', views.RolesView.as_view(), name='roles'),
]
