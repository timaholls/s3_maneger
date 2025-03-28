import os
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import PermissionDenied
from .models import UserPermission, S3ActionLog
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# S3 bucket name
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')

# S3 access credentials
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

# S3 endpoint for TimeWeb Cloud
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', 'https://s3.timeweb.cloud')

# S3 region
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'ru-1')

class S3Service:
    """Класс для работы с S3 хранилищем"""

    def __init__(self):
        """Инициализация клиента S3"""
        self.s3_client = boto3.client(
            's3',
            endpoint_url=AWS_S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_S3_REGION_NAME,
            use_ssl = False,
        )
        self.bucket_name = AWS_STORAGE_BUCKET_NAME

    def check_permission(self, user, folder_path, required_permission):
        """Проверка прав доступа пользователя к папке"""
        if user.is_superuser:
            return True

        # Нормализуем путь к папке
        folder_path = self._normalize_path(folder_path)

        # Получаем все права пользователя
        permissions = UserPermission.objects.filter(user=user)

        # Проверяем права для указанной папки и всех родительских папок
        path_parts = folder_path.split('/')
        for i in range(len(path_parts) + 1):
            check_path = '/'.join(path_parts[:i])
            for perm in permissions:
                if perm.folder_path == check_path:
                    if required_permission == 'read' and perm.can_read:
                        return True
                    if required_permission == 'write' and perm.can_write:
                        return True
                    if required_permission == 'delete' and perm.can_delete:
                        return True

        return False

    def log_action(self, user, action_type, object_path, success=True, ip_address=None, details=None):
        """Логирование действий пользователя"""
        S3ActionLog.objects.create(
            user=user,
            action_type=action_type,
            object_path=object_path,
            success=success,
            ip_address=ip_address,
            details=details
        )

    def list_objects(self, user, prefix='', delimiter='/'):
        """Получение списка объектов в директории"""
        if not self.check_permission(user, prefix, 'read'):
            raise PermissionDenied("У вас нет прав для просмотра содержимого этой папки")

        try:
            # Если префикс не пустой и не заканчивается на '/', добавляем '/'
            if prefix and not prefix.endswith('/'):
                prefix = prefix + '/'

            kwargs = {
                'Bucket': self.bucket_name,
                'Prefix': prefix,
            }

            if delimiter:
                kwargs['Delimiter'] = delimiter

            response = self.s3_client.list_objects_v2(**kwargs)

            # Логируем действие
            self.log_action(user, 'read', prefix)

            # Форматируем результат
            result = {
                'directories': [],
                'files': []
            }

            # Получаем общие префиксы (директории)
            if 'CommonPrefixes' in response:
                for common_prefix in response['CommonPrefixes']:
                    prefix_path = common_prefix['Prefix']
                    dir_name = os.path.basename(os.path.dirname(prefix_path))
                    result['directories'].append({
                        'name': dir_name or prefix_path.rstrip('/').split('/')[-1],
                        'path': prefix_path
                    })

            # Получаем содержимое (файлы)
            if 'Contents' in response:
                for item in response['Contents']:
                    # Пропускаем элемент, если его ключ совпадает с префиксом
                    # (в S3 директории представлены как объекты с именем, оканчивающимся на '/')
                    if item['Key'] == prefix:
                        continue

                    # Убираем префикс из имени файла
                    file_name = item['Key']
                    if prefix:
                        file_name = file_name.replace(prefix, '', 1)

                    # Пропускаем "каталоги"
                    if file_name.endswith('/'):
                        continue

                    result['files'].append({
                        'name': file_name,
                        'path': item['Key'],
                        'size': item['Size'],
                        'last_modified': item['LastModified']
                    })

            return result
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'read', prefix, success=False, details=str(e))
            raise

    def create_folder(self, user, folder_path):
        """Создание новой папки (директории) в S3"""
        if not self.check_permission(user, folder_path, 'write'):
            raise PermissionDenied("У вас нет прав для создания папки")

        # Нормализуем путь и добавляем '/' в конец
        folder_path = self._normalize_path(folder_path)
        if not folder_path.endswith('/'):
            folder_path += '/'

        try:
            # Создаем пустой объект с '/' в конце имени, что представляет собой директорию в S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=''
            )

            # Логируем действие
            self.log_action(user, 'create_folder', folder_path)

            return {
                'success': True,
                'message': f"Папка '{folder_path}' успешно создана"
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'create_folder', folder_path, success=False, details=str(e))
            raise

    def delete_folder(self, user, folder_path):
        """Удаление папки и всего её содержимого из S3"""
        if not self.check_permission(user, folder_path, 'delete'):
            raise PermissionDenied("У вас нет прав для удаления папки")

        # Нормализуем путь и добавляем '/' в конец
        folder_path = self._normalize_path(folder_path)
        if not folder_path.endswith('/'):
            folder_path += '/'

        try:
            # Список объектов для удаления
            objects_to_delete = []

            # Получаем список всех объектов с указанным префиксом
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=folder_path)

            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})

            # Если объекты найдены, удаляем их
            if objects_to_delete:
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )

            # Логируем действие
            self.log_action(user, 'delete_folder', folder_path)

            return {
                'success': True,
                'message': f"Папка '{folder_path}' успешно удалена",
                'deleted_objects_count': len(objects_to_delete)
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'delete_folder', folder_path, success=False, details=str(e))
            raise

    def upload_file(self, user, file_obj, destination_path):
        """Загрузка файла в S3"""
        # Получаем директорию, в которую загружается файл
        folder_path = os.path.dirname(destination_path)

        if not self.check_permission(user, folder_path, 'write'):
            raise PermissionDenied("У вас нет прав для загрузки файлов в эту папку")

        try:
            # Загружаем файл в S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                destination_path
            )

            # Логируем действие
            self.log_action(user, 'upload', destination_path)

            return {
                'success': True,
                'message': f"Файл '{os.path.basename(destination_path)}' успешно загружен",
                'path': destination_path
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'upload', destination_path, success=False, details=str(e))
            raise

    def delete_file(self, user, file_path):
        """Удаление файла из S3"""
        # Получаем директорию, в которой находится файл
        folder_path = os.path.dirname(file_path)

        if not self.check_permission(user, folder_path, 'delete'):
            raise PermissionDenied("У вас нет прав для удаления файлов из этой папки")

        try:
            # Удаляем файл из S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )

            # Логируем действие
            self.log_action(user, 'delete', file_path)

            return {
                'success': True,
                'message': f"Файл '{os.path.basename(file_path)}' успешно удален"
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'delete', file_path, success=False, details=str(e))
            raise

    def generate_download_url(self, user, file_path, expires_in=3600):
        """Генерация временной ссылки для скачивания файла"""
        # Получаем директорию, в которой находится файл
        folder_path = os.path.dirname(file_path)

        if not self.check_permission(user, folder_path, 'read'):
            raise PermissionDenied("У вас нет прав для скачивания файлов из этой папки")

        try:
            # Генерируем временную ссылку для скачивания
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': file_path},
                ExpiresIn=expires_in
            )

            # Логируем действие
            self.log_action(user, 'download', file_path)

            return {
                'success': True,
                'url': url,
                'expires_in': expires_in
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'download', file_path, success=False, details=str(e))
            raise

    def _normalize_path(self, path):
        """Нормализация пути к объекту/директории"""
        # Удаляем лишние слэши в начале пути
        path = path.lstrip('/')

        # Если путь пустой, возвращаем корневую директорию
        if not path:
            return ''

        return path
