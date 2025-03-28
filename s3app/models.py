from django.db import models
from django.contrib.auth.models import User


class UserPermission(models.Model):
    """Модель для хранения прав доступа пользователей к папкам в S3"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='s3_permissions',
                           verbose_name='Пользователь')
    folder_path = models.CharField(max_length=255, verbose_name='Путь к папке в S3')
    can_read = models.BooleanField(default=True, verbose_name='Может читать')
    can_write = models.BooleanField(default=False, verbose_name='Может записывать')
    can_delete = models.BooleanField(default=False, verbose_name='Может удалять')

    class Meta:
        unique_together = ('user', 'folder_path')
        verbose_name = 'Право доступа'
        verbose_name_plural = 'Права доступа'

    def __str__(self):
        return f"{self.user.username} - {self.folder_path}"


class S3ActionLog(models.Model):
    """Модель для хранения логов действий пользователей в S3"""
    ACTION_TYPES = (
        ('read', 'Чтение'),
        ('upload', 'Загрузка'),
        ('download', 'Скачивание'),
        ('delete', 'Удаление'),
        ('create_folder', 'Создание папки'),
        ('delete_folder', 'Удаление папки'),
    )

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='s3_logs',
                            verbose_name='Пользователь')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name='Тип действия')
    object_path = models.CharField(max_length=255, verbose_name='Путь к объекту в S3')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Время действия')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP адрес')
    success = models.BooleanField(default=True, verbose_name='Успешно')
    details = models.TextField(blank=True, null=True, verbose_name='Детали')

    class Meta:
        verbose_name = 'Лог действия'
        verbose_name_plural = 'Логи действий'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username if self.user else 'Аноним'} - {self.get_action_type_display()} - {self.object_path}"
