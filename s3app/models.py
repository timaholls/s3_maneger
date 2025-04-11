from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

class UserPermission(models.Model):
    """Модель для хранения прав доступа пользователей к директориям S3"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    folder_path = models.CharField(max_length=1024, blank=True, default='', verbose_name="Путь к папке")
    can_read = models.BooleanField(default=True, verbose_name="Чтение")
    can_write = models.BooleanField(default=False, verbose_name="Запись")
    can_delete = models.BooleanField(default=False, verbose_name="Удаление")
    can_move = models.BooleanField(default=False, verbose_name="Перемещение")  # Новое право для перемещения файлов и папок

    class Meta:
        verbose_name = "Право доступа"
        verbose_name_plural = "Права доступа"
        unique_together = ('user', 'folder_path')

    def __str__(self):
        path_display = self.folder_path if self.folder_path else '/ (корень)'
        permissions = []
        if self.can_read:
            permissions.append('Чтение')
        if self.can_write:
            permissions.append('Запись')
        if self.can_delete:
            permissions.append('Удаление')
        if self.can_move:
            permissions.append('Перемещение')
        return f"{self.user.username} - {path_display} - {', '.join(permissions)}"


class S3ActionLog(models.Model):
    """Модель для логирования действий пользователей с S3"""
    ACTION_TYPES = [
        ('read', 'Чтение/Просмотр'),
        ('write', 'Запись/Загрузка'),
        ('delete', 'Удаление'),
        ('create_folder', 'Создание папки'),
        ('list', 'Просмотр содержимого'),
        ('download', 'Скачивание'),
        ('search', 'Поиск'),
        ('upload', 'Загрузка файла'),
        ('restore', 'Восстановление из корзины'),
        ('move', 'Перемещение'),  # Добавлено новое действие 'Перемещение'
        ('sign_document', 'Подписание документа'),  # Новый тип действия
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Пользователь")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время действия")
    action = models.CharField(max_length=20, choices=ACTION_TYPES, verbose_name="Тип действия")
    path = models.CharField(max_length=1024, blank=True, default='', verbose_name="Путь объекта")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP адрес")
    success = models.BooleanField(default=True, verbose_name="Успешно")
    details = models.TextField(blank=True, null=True, verbose_name="Детали")

    class Meta:
        verbose_name = "Лог действия"
        verbose_name_plural = "Логи действий"
        ordering = ['-timestamp']  # Сортировка по убыванию времени

    def __str__(self):
        return f"{self.timestamp} - {self.user} - {self.get_action_display()} - {self.path}"


class TrashItem(models.Model):
    """Модель для хранения информации об удаленных объектах в корзине"""
    OBJECT_TYPES = [
        ('file', 'Файл'),
        ('folder', 'Папка'),
    ]

    original_path = models.CharField(max_length=1024, verbose_name="Исходный путь")
    trash_path = models.CharField(max_length=1024, verbose_name="Путь в корзине")
    object_type = models.CharField(max_length=10, choices=OBJECT_TYPES, verbose_name="Тип объекта")
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Удалено пользователем")
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name="Время удаления")
    original_size = models.BigIntegerField(default=0, verbose_name="Размер объекта")
    expires_at = models.DateTimeField(verbose_name="Срок хранения до")

    class Meta:
        verbose_name = "Элемент корзины"
        verbose_name_plural = "Элементы корзины"
        ordering = ['-deleted_at']  # Сортировка по убыванию времени удаления

    def __str__(self):
        return f"{self.get_object_type_display()} - {self.original_path} (удалено {self.deleted_at})"

    def is_expired(self):
        """Проверяет, истек ли срок хранения объекта в корзине"""
        return timezone.now() > self.expires_at

    def days_left(self):
        """Возвращает количество дней до истечения срока хранения"""
        if self.is_expired():
            return 0
        delta = self.expires_at - timezone.now()
        return max(0, delta.days)

    @classmethod
    def get_expired_items(cls):
        """Возвращает список элементов с истекшим сроком хранения"""
        return cls.objects.filter(expires_at__lt=timezone.now())

    @classmethod
    def cleanup_expired(cls):
        """Удаляет из БД записи с истекшим сроком хранения"""
        expired_items = cls.get_expired_items()
        result = {
            'count': expired_items.count(),
            'items': list(expired_items.values_list('trash_path', flat=True))
        }
        expired_items.delete()
        return result


class DocumentSignature(models.Model):
    """Модель для хранения информации о документах, требующих подписи"""
    DOCUMENT_TYPES = [
        ('upload', 'Для загрузки'),
        ('download', 'Для скачивания'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Ожидает подписи'),
        ('signed', 'Подписан'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    title = models.CharField(max_length=255, verbose_name="Название документа")
    document_path = models.CharField(max_length=1024, verbose_name="Путь к документу")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, verbose_name="Тип документа")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    signed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата подписания")

    class Meta:
        verbose_name = "Документ для подписи"
        verbose_name_plural = "Документы для подписи"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username} ({self.get_status_display()})"

    def sign(self):
        """Помечает документ как подписанный и сохраняет время подписания"""
        self.status = 'signed'
        self.signed_at = timezone.now()
        self.save()

    @classmethod
    def has_pending_documents(cls, user):
        """Проверяет, есть ли у пользователя документы, ожидающие подписи"""
        return cls.objects.filter(user=user, status='pending').exists()
