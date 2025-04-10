from django.contrib import admin
from .models import UserPermission, S3ActionLog, TrashItem


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'folder_path', 'can_read', 'can_write', 'can_delete')
    list_filter = ('can_read', 'can_write', 'can_delete')
    search_fields = ('user__username', 'folder_path')


@admin.register(S3ActionLog)
class S3ActionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'path', 'timestamp', 'success', 'ip_address')
    list_filter = ('action', 'success', 'timestamp')
    search_fields = ('user__username', 'path', 'details')
    readonly_fields = ('user', 'action', 'path', 'timestamp', 'success', 'ip_address', 'details')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TrashItem)
class TrashItemAdmin(admin.ModelAdmin):
    list_display = ('object_type', 'original_path', 'deleted_by', 'deleted_at', 'expires_at', 'days_left')
    list_filter = ('object_type', 'deleted_at', 'expires_at')
    search_fields = ('original_path', 'trash_path', 'deleted_by__username')
    readonly_fields = ('original_path', 'trash_path', 'object_type', 'deleted_by', 'deleted_at', 'original_size', 'expires_at')
    date_hierarchy = 'deleted_at'

    def has_add_permission(self, request):
        return False