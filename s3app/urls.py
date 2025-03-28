from django.urls import path
from . import views

app_name = 's3app'

urlpatterns = [
    # Маршруты для авторизации
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Маршруты для работы с файлами/папками в S3
    path('', views.browser_view, name='browser'),
    path('browser/', views.browser_view, name='browser'),  # для корня
    path('browser/<path:path>/', views.browser_view, name='browser_path'),
    path('create-folder/', views.create_folder, name='create_folder'),
    # Изменяем этот маршрут, чтобы он принимал пустой параметр path
    path('create-folder/<path:path>/', views.create_folder, name='create_folder_path'),
    path('delete-folder/<path:path>/', views.delete_folder, name='delete_folder'),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('upload-file/<path:path>/', views.upload_file, name='upload_file_path'),
    path('delete-file/<path:path>/', views.delete_file, name='delete_file'),
    path('download-file/<path:path>/', views.download_file, name='download_file'),

    # Маршруты для управления пользователями
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/permissions/', views.user_permissions, name='user_permissions'),
    path('permissions/<int:perm_id>/delete/', views.delete_permission, name='delete_permission'),

    # Маршруты для просмотра логов
    path('logs/', views.action_logs, name='action_logs'),
]
