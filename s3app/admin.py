from django.contrib import admin
from .models import UserPermission, S3ActionLog


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'folder_path', 'can_read', 'can_write', 'can_delete')
    list_filter = ('can_read', 'can_write', 'can_delete')
    search_fields = ('user__username', 'folder_path')


@admin.register(S3ActionLog)
class S3ActionLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'object_path', 'timestamp', 'success', 'ip_address')
    list_filter = ('action_type', 'success', 'timestamp')
    search_fields = ('user__username', 'object_path', 'details')
    readonly_fields = ('user', 'action_type', 'object_path', 'timestamp', 'success', 'ip_address', 'details')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
