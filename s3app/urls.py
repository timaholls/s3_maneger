from django.urls import path
from . import views
from django.views.generic.base import RedirectView
from django.contrib.auth import views as auth_views
from .forms import CustomPasswordChangeForm  # Импортируйте вашу форму

app_name = 's3app'

urlpatterns = [
    # Маршруты для авторизации
    path('', RedirectView.as_view(pattern_name='s3app:login'), name='index'),  # Redirect root to login
    path('login/', views.login_view, name='login'),  # Explicit login path
    path('logout/', views.logout_view, name='logout'),
    path('redirect/', views.redirect_after_login, name='redirect_after_login'),  # Новый маршрут для перенаправления после входа

    # --- Маршруты для проверки браузера ---
    path('browser-challenge/', views.browser_challenge_page_view, name='browser_challenge_page'),
    path('browser-challenge/validate/', views.browser_challenge_validate_view, name='browser_challenge_validate'),

    # Маршруты для работы с файлами/папками в S3
    path('browser/', views.browser_view, name='browser'),  # Handles root: /browser/
    path('browser/<path:path>/', views.browser_view, name='browser'),  # Handles paths: /browser/some/path/
    path('create-folder/', views.create_folder, name='create_folder'),
    # Изменяем этот маршрут, чтобы он принимал пустой параметр path
    path('create-folder/<path:path>/', views.create_folder, name='create_folder_path'),
    path('delete-folder/<path:path>/', views.delete_folder, name='delete_folder'),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('upload-file/<path:path>/', views.upload_file, name='upload_file_path'),
    path('delete-file/<path:path>/', views.delete_file, name='delete_file'),
    path('download-file/<path:path>/', views.download_file, name='download_file'),

    # Маршруты для перемещения файлов и папок
    path('move-file/<path:path>/', views.move_file, name='move_file'),
    path('move-folder/<path:path>/', views.move_folder, name='move_folder'),
    path('move-multiple/', views.move_multiple, name='move_multiple'),

    # Добавляем новые URL для множественных операций
    path('download-multiple/', views.download_multiple, name='download_multiple'),
    path('delete-multiple/', views.delete_multiple, name='delete_multiple'),

    # --- Новые URL для смены пароля ---
    path('password_change/',
         auth_views.PasswordChangeView.as_view(
             form_class=CustomPasswordChangeForm,  # Используйте вашу форму
             template_name='password_change_form.html',
             success_url='../password_change/done/'
         ),
         name='password_change'),
    path('password_change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='password_change_done.html'
         ),
         name='password_change_done'),
    # --- Конец URL для смены пароля ---

    # Маршруты для управления пользователями
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/permissions/', views.user_permissions, name='user_permissions'),
    path('permissions/<int:perm_id>/delete/', views.delete_permission, name='delete_permission'),

    # Маршруты для просмотра логов
    path('logs/', views.action_logs, name='action_logs'),

    # Новый маршрут для автозаполнения папок
    path('folders-autocomplete/', views.folders_autocomplete, name='folders_autocomplete'),

    # Корзина (только для администраторов)
    path('trash/', views.trash_view, name='trash'),
    path('trash/restore/<int:item_id>/', views.restore_from_trash, name='restore_from_trash'),
    path('trash/delete/<int:item_id>/', views.delete_from_trash, name='delete_from_trash'),
    path('trash/empty/', views.empty_trash, name='empty_trash'),
    path('trash/cleanup-expired/', views.cleanup_expired_trash, name='cleanup_expired_trash'),
]
