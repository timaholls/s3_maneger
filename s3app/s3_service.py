import os
import boto3
import uuid
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone
import datetime
from .models import UserPermission, S3ActionLog, TrashItem
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
        print(f"--- Checking permission ---")  # DEBUG
        print(f"User: {user.username} ({user.id})")  # DEBUG
        print(f"Requested Path: '{folder_path}'")  # DEBUG
        print(f"Required Permission: '{required_permission}'")  # DEBUG

        if user.is_superuser:
            print("User is superuser. Access granted.")  # DEBUG
            return True

        # Нормализуем путь к папке
        normalized_path = self._normalize_path(folder_path)
        print(f"Normalized Path: '{normalized_path}'")  # DEBUG

        # Получаем все права пользователя
        permissions = UserPermission.objects.filter(user=user)
        print(
            f"All permissions found for user: {list(permissions.values_list('folder_path', 'can_read', 'can_write', 'can_delete'))}")  # DEBUG

        # Проверяем права для указанной папки и всех родительских папок
        check_path = normalized_path
        while True:
            print(f"  Checking path: '{check_path}'")  # DEBUG
            # Оптимизация: Получаем права для текущего пути за один запрос
            perm_for_path = permissions.filter(folder_path=check_path).first()

            if perm_for_path:
                print(
                    f"    Found permission object for '{check_path}': ID={perm_for_path.id}, Read={perm_for_path.can_read}, Write={perm_for_path.can_write}, Delete={perm_for_path.can_delete}")  # DEBUG
                if required_permission == 'read' and perm_for_path.can_read:
                    print(f"    Read permission sufficient. Access granted.")  # DEBUG
                    return True
                if required_permission == 'write' and perm_for_path.can_write:
                    print(f"    Write permission sufficient. Access granted.")  # DEBUG
                    return True
                if required_permission == 'delete' and perm_for_path.can_delete:
                    print(f"    Delete permission sufficient. Access granted.")  # DEBUG
                    return True
                # Если нашли права, но нужного нет
                print(
                    f"    Permission found for '{check_path}', but not the required '{required_permission}'.")  # DEBUG

            else:
                print(f"    No specific permission found for path '{check_path}'.")  # DEBUG

            # Если дошли до корня ('') и права не найдены или не подходят
            if check_path == '':
                print(
                    f"  Reached root (''). Permission check failed for original path '{normalized_path}'. Access denied.")  # DEBUG
                return False

            # Переходим к родительской папке
            parent_path = '/'.join(check_path.split('/')[:-1])
            print(f"  Moving to parent path: '{parent_path}'")  # DEBUG
            # Предотвращаем зацикливание
            if parent_path == check_path:
                print(f"  Parent path is the same as current path. Stopping check. Access denied.")  # DEBUG
                return False
            check_path = parent_path

        # Если цикл завершился без return True (не должно произойти из-за проверки check_path == '')
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
        """Получение списка объектов в директории (с пагинацией S3)"""
        normalized_prefix = self._normalize_path(prefix)
        print(normalized_prefix)
        if not self.check_permission(user, normalized_prefix, 'read'):
            raise PermissionDenied("У вас нет прав для просмотра содержимого этой папки")

        # Если префикс не пустой и не заканчивается на '/', добавляем '/'
        # Это важно для корректной работы Delimiter
        s3_prefix = normalized_prefix
        if s3_prefix and not s3_prefix.endswith('/'):
            s3_prefix += '/'

        result = {
            'directories': [],
            'files': []
        }
        processed_dirs = set()

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=s3_prefix,
                Delimiter=delimiter  # Keep delimiter for browsing
            )

            for page in pages:
                # Получаем общие префиксы (директории)
                if 'CommonPrefixes' in page:
                    for common_prefix in page['CommonPrefixes']:
                        prefix_path = common_prefix['Prefix']
                        # Проверяем, не обработали ли уже эту директорию
                        if prefix_path not in processed_dirs:
                            # Извлекаем имя последней части пути
                            dir_name = prefix_path.rstrip('/').split('/')[-1]
                            result['directories'].append({
                                'name': dir_name,
                                'path': prefix_path.rstrip('/') # Сохраняем путь без слеша на конце для консистентности
                            })
                            processed_dirs.add(prefix_path)
                # Получаем содержимое (файлы и "пустые" объекты папок)
                if 'Contents' in page:
                    for item in page['Contents']:
                        item_key = item['Key']

                        # Пропускаем сам объект текущей директории (если он есть)
                        # Например, при prefix='folder/' может вернуться объект с Key='folder/'
                        if item_key == s3_prefix:
                            continue

                        # Извлекаем имя файла/объекта относительно текущего префикса
                        relative_name = item_key
                        if s3_prefix:
                             # Убедимся, что заменяем только в начале строки
                            if relative_name.startswith(s3_prefix):
                                relative_name = relative_name[len(s3_prefix):]

                        # Если после удаления префикса осталась пустая строка - пропускаем
                        if not relative_name:
                            continue

                        # Пропускаем "подпапки", если они представлены как объекты (например, 'subdir/')
                        # Они уже должны быть обработаны через CommonPrefixes
                        # Также пропускаем, если имя содержит '/', но не является файлом (размер 0 и оканчивается на '/')
                        # Это может произойти, если Delimiter не сработал ожидаемо или объект создан некорректно
                        if relative_name.endswith('/') and item['Size'] == 0:
                            # Дополнительно проверим, нет ли уже такой директории из CommonPrefixes
                            dir_path_check = item_key.rstrip('/')
                            if not any(d['path'] == dir_path_check for d in result['directories']):
                                # Если вдруг папка не пришла в CommonPrefixes, добавим ее
                                dir_name = relative_name.rstrip('/')
                                result['directories'].append({
                                    'name': dir_name,
                                    'path': dir_path_check
                                })
                                processed_dirs.add(item_key) # Добавляем полный ключ с /
                            continue # Пропускаем добавление в files

                        # Если это не папка, добавляем в файлы
                        result['files'].append({
                            'name': relative_name, # Имя относительно текущей папки
                            'path': item_key,      # Полный путь (Key) от корня бакета
                            'size': item['Size'],
                            'last_modified': item['LastModified']
                        })

            # Логируем успешное действие после получения всех данных
            self.log_action(user, 'list', s3_prefix or '(root)')  # Changed action type slightly

            result['directories'].sort(key=lambda x: x['name'])
            result['files'].sort(key=lambda x: x['name'])

            return result
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'read', s3_prefix or '(root)', success=False, details=str(e))
            raise
        except PermissionDenied as e: # Перехватываем PermissionDenied, чтобы залогировать его
            self.log_action(user, 'read', s3_prefix or '(root)', success=False, details=f"Permission denied: {str(e)}")
            raise

    def search_objects(self, user, prefix='', query='', max_results=200):
        """Рекурсивный поиск объектов (файлов И ПАПОК) по имени в указанной директории и поддиректориях."""
        normalized_prefix = self._normalize_path(prefix)
        query_lower = query.lower().strip()

        if not query_lower:
            return []  # Return empty if query is empty

        # Check permission for the starting path of the search
        if not self.check_permission(user, normalized_prefix, 'read'):
            # Log the failed attempt due to permissions before raising
            self.log_action(user, 'search', f"{normalized_prefix} (query: {query})", success=False,
                            details="Permission denied to read search path")
            raise PermissionDenied(f"У вас нет прав для поиска в папке '{normalized_prefix or 'Корень'}'")

        s3_prefix = normalized_prefix
        if s3_prefix and not s3_prefix.endswith('/'):
            s3_prefix += '/'

        found_items = []
        scanned_count = 0

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            # No Delimiter specified for recursive listing
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=s3_prefix
            )

            for page in pages:
                if 'Contents' in page:
                    for item in page['Contents']:
                        scanned_count += 1
                        item_key = item['Key']

                        # Skip the containing folder object itself (prefix object)
                        if item_key == s3_prefix:
                            continue

                        # Determine if it's a folder (ends with / and usually size 0)
                        # We primarily rely on the trailing slash convention
                        is_folder = item_key.endswith('/')

                        # Extract the name part for matching
                        # For folders 'path/to/folder/', basename needs the key without trailing slash
                        item_name = os.path.basename(item_key.rstrip('/'))

                        # Skip if somehow the name is empty after stripping/basename
                        if not item_name:
                            continue

                        # Check if the item_name (file or folder) contains the query
                        if query_lower in item_name.lower():
                            # Optional: Check read permission on the specific parent folder
                            # parent_folder = os.path.dirname(item_key.rstrip('/'))
                            # if not self.check_permission(user, parent_folder, 'read'):
                            #    continue # Skip if no permission

                            # Prepare item data
                            item_data = {
                                'name': item_name,           # Just the name part
                                'path': item_key,           # Full S3 key (needed for actions)
                                'display_path': item_key,   # Path to show the user (full key)
                                'is_folder': is_folder,     # Flag to distinguish type
                            }

                            # Add file-specific or folder-specific data
                            if is_folder:
                                item_data['size'] = None # Folders don't have relevant size
                                # Folders (objects ending in /) do have LastModified,
                                # but it might be confusing, set to None or keep item['LastModified']
                                item_data['last_modified'] = None # item['LastModified']
                            else:
                                item_data['size'] = item['Size']
                                item_data['last_modified'] = item['LastModified']

                            found_items.append(item_data)

                            # Stop if we have enough results
                            if len(found_items) >= max_results:
                                break # Stop processing this page
                # Stop iterating through pages if we hit the limit
                if len(found_items) >= max_results:
                    break

            # Log the search action
            self.log_action(user, 'search', f"{s3_prefix or '(root)'} (query: {query})", success=True,
                            details=f"Found {len(found_items)} items (scanned approx {scanned_count})")

            # Sort results by full path for consistency
            found_items.sort(key=lambda x: x['path'])

            return found_items

        except ClientError as e:
            self.log_action(user, 'search', f"{s3_prefix or '(root)'} (query: {query})", success=False, details=str(e))
            raise  # Re-raise the exception
        except PermissionDenied as e:  # Should be caught earlier, but just in case
            self.log_action(user, 'search', f"{s3_prefix or '(root)'} (query: {query})", success=False,
                            details=f"Permission denied during search: {str(e)}")
            raise

    def create_folder(self, user, folder_path):
        """Создание новой папки (директории) в S3"""
        # Нормализуем путь ДО проверки прав
        normalized_path = self._normalize_path(folder_path)
        # Права проверяем на родительскую папку
        parent_path = os.path.dirname(normalized_path)

        if not self.check_permission(user, parent_path, 'write'):
             # Если нет прав на запись в родительскую, проверяем права на саму папку (вдруг создаем папку, на которую уже дали права)
             # Это менее типичный сценарий, но возможный
            if not self.check_permission(user, normalized_path, 'write'):
                raise PermissionDenied("У вас нет прав для создания папки в этом расположении")

        # Добавляем '/' в конец для S3
        s3_folder_key = normalized_path
        if not s3_folder_key.endswith('/'):
            s3_folder_key += '/'

        try:
            # Проверяем, существует ли уже объект с таким ключом
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_folder_key)
                # Если head_object успешен, папка (или файл с таким именем!) уже существует
                return {
                    'success': False,
                    'message': f"Папка или файл с именем '{normalized_path}' уже существует."
                }
            except ClientError as e:
                # Если получаем 404, значит объекта нет - это то, что нам нужно
                if e.response['Error']['Code'] == '404':
                    pass
                else:
                    # Если другая ошибка при проверке - пробрасываем ее
                    raise

            # Создаем пустой объект с '/' в конце имени
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_folder_key,
                Body=''
            )

            # Логируем действие
            self.log_action(user, 'create_folder', s3_folder_key)

            return {
                'success': True,
                'message': f"Папка '{normalized_path}' успешно создана" # Показываем пользователю путь без /
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'create_folder', s3_folder_key, success=False, details=str(e))
            raise

    def delete_file(self, user, file_path):
        """Удаление файла из S3 (перемещение в корзину)"""
        normalized_file_path = self._normalize_path(file_path)
        # Получаем директорию, в которой находится файл
        folder_path = os.path.dirname(normalized_file_path)

        # Проверяем, не является ли путь папкой (оканчивается на '/')
        if normalized_file_path.endswith('/'):
             self.log_action(user, 'delete', normalized_file_path, success=False, details="Attempted to delete a folder using delete_file method.")
             raise ValueError("Для удаления папок используйте метод delete_folder")

        if not self.check_permission(user, folder_path, 'delete'):
            raise PermissionDenied("У вас нет прав для удаления файлов из этой папки")

        try:
            # Получаем информацию о файле перед удалением
            file_info = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=normalized_file_path
            )
            file_size = file_info.get('ContentLength', 0)

            # Генерируем уникальный путь в корзине
            trash_path = f"__trash/{uuid.uuid4().hex}/{os.path.basename(normalized_file_path)}"

            # Копируем файл в корзину
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource=f"{self.bucket_name}/{normalized_file_path}",
                Key=trash_path
            )

            # Удаляем оригинальный файл
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=normalized_file_path # Используем нормализованный путь
            )

            # Создаем запись в таблице корзины
            expiration_date = timezone.now() + datetime.timedelta(days=30)
            TrashItem.objects.create(
                original_path=normalized_file_path,
                trash_path=trash_path,
                object_type='file',
                deleted_by=user,
                original_size=file_size,
                expires_at=expiration_date
            )

            # Логируем действие
            self.log_action(user, 'delete', normalized_file_path)

            return {
                'success': True,
                'message': f"Файл '{os.path.basename(normalized_file_path)}' перемещен в корзину"
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'delete', normalized_file_path, success=False, details=str(e))
            raise

    def delete_folder(self, user, folder_path):
        """Удаление папки и всего её содержимого из S3 (перемещение в корзину)"""
        normalized_path = self._normalize_path(folder_path)

        # Права проверяем на саму папку, которую удаляем
        if not self.check_permission(user, normalized_path, 'delete'):
            raise PermissionDenied("У вас нет прав для удаления этой папки")

        # Добавляем '/' в конец, чтобы использовать как префикс
        s3_prefix = normalized_path
        if not s3_prefix.endswith('/'):
            s3_prefix += '/'

        try:
            # Получаем общий размер всех объектов в папке
            total_size = 0
            objects_to_move = []

            # Используем пагинатор для получения ВСЕХ объектов с этим префиксом
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=s3_prefix)

            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_move.append(obj)
                        total_size += obj.get('Size', 0)

            # Генерируем уникальный идентификатор для корзины
            trash_id = uuid.uuid4().hex

            # Перемещаем все объекты в корзину и удаляем оригиналы
            for obj in objects_to_move:
                original_key = obj['Key']
                relative_path = original_key[len(s3_prefix):] if len(s3_prefix) > 0 and original_key.startswith(s3_prefix) else original_key
                trash_key = f"__trash/{trash_id}/{normalized_path}/{relative_path}"

                # Копируем объект в корзину
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource=f"{self.bucket_name}/{original_key}",
                    Key=trash_key
                )

                # Удаляем оригинальный объект
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=original_key
                )

            # Создаем запись в таблице корзины
            expiration_date = timezone.now() + datetime.timedelta(days=30)
            trash_prefix = f"__trash/{trash_id}/{normalized_path}/"
            TrashItem.objects.create(
                original_path=normalized_path,
                trash_path=trash_prefix,
                object_type='folder',
                deleted_by=user,
                original_size=total_size,
                expires_at=expiration_date
            )

            # Логируем действие
            self.log_action(user, 'delete', s3_prefix)

            return {
                'success': True,
                'message': f"Папка '{normalized_path}' и ее содержимое ({len(objects_to_move)} объектов) перемещены в корзину",
                'deleted_objects_count': len(objects_to_move)
            }
        except ClientError as e:
            # Логируем неудачное действие
            self.log_action(user, 'delete', s3_prefix, success=False, details=str(e))
            raise

    def list_trash_items(self):
        """Получение списка элементов в корзине"""
        try:
            # Получаем записи из БД
            trash_items = TrashItem.objects.all().order_by('-deleted_at')
            return trash_items
        except Exception as e:
            print(f"Error listing trash items: {str(e)}")
            return []

    def restore_from_trash(self, user, trash_item_id):
        """Восстановление элемента из корзины"""
        try:
            # Получаем запись из БД
            trash_item = TrashItem.objects.get(id=trash_item_id)

            if trash_item.object_type == 'file':
                # Восстановление файла
                original_path = trash_item.original_path
                trash_path = trash_item.trash_path

                # Проверяем, существует ли уже файл с таким путем
                try:
                    self.s3_client.head_object(
                        Bucket=self.bucket_name,
                        Key=original_path
                    )
                    # Если файл уже существует, добавляем к имени '_restored'
                    filename, ext = os.path.splitext(original_path)
                    original_path = f"{filename}_restored{ext}"
                except ClientError as e:
                    if e.response['Error']['Code'] != '404':
                        raise

                # Копируем объект из корзины в исходное расположение
                self.s3_client.copy_object(
                    Bucket=self.bucket_name,
                    CopySource=f"{self.bucket_name}/{trash_path}",
                    Key=original_path
                )

                # Удаляем объект из корзины
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=trash_path
                )

                # Логируем действие
                self.log_action(user, 'restore', original_path)

                # Удаляем запись из БД
                trash_item.delete()

                return {
                    'success': True,
                    'message': f"Файл '{os.path.basename(original_path)}' успешно восстановлен",
                    'restored_path': original_path
                }

            elif trash_item.object_type == 'folder':
                # Восстановление папки
                original_path = trash_item.original_path
                trash_path = trash_item.trash_path.rstrip('/')

                # Получаем все объекты в корзине с этим префиксом
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=trash_path)

                restored_count = 0
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            trash_key = obj['Key']

                            # Пропускаем сам префикс
                            if trash_key == trash_path:
                                continue

                            # Определяем исходный путь
                            relative_path = trash_key[len(trash_path)+1:] if trash_key.startswith(trash_path+'/') else ''
                            target_key = f"{original_path}/{relative_path}" if original_path else relative_path

                            # Копируем объект из корзины в исходное расположение
                            self.s3_client.copy_object(
                                Bucket=self.bucket_name,
                                CopySource=f"{self.bucket_name}/{trash_key}",
                                Key=target_key
                            )

                            # Удаляем объект из корзины
                            self.s3_client.delete_object(
                                Bucket=self.bucket_name,
                                Key=trash_key
                            )

                            restored_count += 1

                # Логируем действие
                self.log_action(user, 'restore', original_path)

                # Удаляем запись из БД
                trash_item.delete()

                return {
                    'success': True,
                    'message': f"Папка '{original_path}' и ее содержимое ({restored_count} объектов) успешно восстановлены",
                    'restored_path': original_path,
                    'restored_count': restored_count
                }

            else:
                return {
                    'success': False,
                    'message': f"Неизвестный тип объекта: {trash_item.object_type}"
                }

        except TrashItem.DoesNotExist:
            return {
                'success': False,
                'message': "Элемент не найден в корзине"
            }
        except ClientError as e:
            return {
                'success': False,
                'message': f"Ошибка восстановления: {str(e)}"
            }

    def delete_from_trash(self, trash_item_id):
        """Окончательное удаление элемента из корзины"""
        try:
            # Получаем запись из БД
            trash_item = TrashItem.objects.get(id=trash_item_id)
            trash_path = trash_item.trash_path

            if trash_item.object_type == 'file':
                # Удаляем файл из корзины
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=trash_path
                )

                # Удаляем запись из БД
                trash_item.delete()

                return {
                    'success': True,
                    'message': f"Файл '{os.path.basename(trash_item.original_path)}' окончательно удален из корзины"
                }

            elif trash_item.object_type == 'folder':
                # Удаляем все объекты с этим префиксом
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.bucket_name, Prefix=trash_path)

                deleted_count = 0
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            self.s3_client.delete_object(
                                Bucket=self.bucket_name,
                                Key=obj['Key']
                            )
                            deleted_count += 1

                # Удаляем запись из БД
                trash_item.delete()

                return {
                    'success': True,
                    'message': f"Папка '{trash_item.original_path}' и ее содержимое ({deleted_count} объектов) окончательно удалены из корзины",
                    'deleted_count': deleted_count
                }

            else:
                return {
                    'success': False,
                    'message': f"Неизвестный тип объекта: {trash_item.object_type}"
                }

        except TrashItem.DoesNotExist:
            return {
                'success': False,
                'message': "Элемент не найден в корзине"
            }
        except ClientError as e:
            return {
                'success': False,
                'message': f"Ошибка удаления: {str(e)}"
            }

    def empty_trash(self):
        """Полная очистка корзины"""
        try:
            # Получаем все записи из корзины
            trash_items = TrashItem.objects.all()
            deleted_count = 0

            for item in trash_items:
                trash_path = item.trash_path

                if item.object_type == 'file':
                    # Удаляем файл из корзины
                    self.s3_client.delete_object(
                        Bucket=self.bucket_name,
                        Key=trash_path
                    )
                    deleted_count += 1

                elif item.object_type == 'folder':
                    # Удаляем все объекты с этим префиксом
                    paginator = self.s3_client.get_paginator('list_objects_v2')
                    pages = paginator.paginate(Bucket=self.bucket_name, Prefix=trash_path)

                    for page in pages:
                        if 'Contents' in page:
                            for obj in page['Contents']:
                                self.s3_client.delete_object(
                                    Bucket=self.bucket_name,
                                    Key=obj['Key']
                                )
                                deleted_count += 1

            # Удаляем все записи из БД
            items_count = trash_items.count()
            trash_items.delete()

            return {
                'success': True,
                'message': f"Корзина очищена. Удалено {items_count} элементов ({deleted_count} объектов).",
                'deleted_count': deleted_count
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Ошибка очистки корзины: {str(e)}"
            }

    def cleanup_expired_trash(self):
        """Очистка элементов корзины с истекшим сроком хранения"""
        try:
            # Получаем элементы с истекшим сроком хранения
            expired_items = TrashItem.get_expired_items()
            deleted_count = 0

            for item in expired_items:
                trash_path = item.trash_path

                if item.object_type == 'file':
                    # Удаляем файл из корзины
                    self.s3_client.delete_object(
                        Bucket=self.bucket_name,
                        Key=trash_path
                    )
                    deleted_count += 1

                elif item.object_type == 'folder':
                    # Удаляем все объекты с этим префиксом
                    paginator = self.s3_client.get_paginator('list_objects_v2')
                    pages = paginator.paginate(Bucket=self.bucket_name, Prefix=trash_path)

                    for page in pages:
                        if 'Contents' in page:
                            for obj in page['Contents']:
                                self.s3_client.delete_object(
                                    Bucket=self.bucket_name,
                                    Key=obj['Key']
                                )
                                deleted_count += 1

            # Удаляем записи из БД
            items_count = expired_items.count()
            expired_items.delete()

            return {
                'success': True,
                'message': f"Очищены элементы с истекшим сроком хранения: {items_count} элементов ({deleted_count} объектов).",
                'deleted_count': deleted_count
            }

        except Exception as e:
            return {
                'success': False,
                'message': f"Ошибка очистки элементов с истекшим сроком хранения: {str(e)}"
            }

    def _normalize_path(self, path):
        """Нормализация пути к объекту/директории.
           Удаляет начальные/конечные слеши и множественные слеши."""
        if not path:
            return ''
        # Заменяем множественные слеши на один
        path = '/'.join(filter(None, path.split('/')))
        return path

    def list_all_folders(self):
        """Получение списка всех папок в хранилище для автозаполнения"""
        folders = set([''])  # Включаем корневую папку

        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Delimiter='/'
            )

            # Обрабатываем первый уровень папок
            for page in pages:
                if 'CommonPrefixes' in page:
                    for prefix in page['CommonPrefixes']:
                        prefix_path = prefix['Prefix'].rstrip('/')
                        folders.add(prefix_path)

                        # Рекурсивно получаем подпапки
                        self._get_subfolders(prefix_path, folders)

            # Преобразуем set в список и сортируем
            folders_list = sorted(list(folders))

            return folders_list

        except ClientError as e:
            print(f"Error listing all folders: {str(e)}")
            return []

    def _get_subfolders(self, parent_path, folders_set):
        """Рекурсивное получение подпапок для указанного пути"""
        try:
            # Добавляем слеш в конец для получения содержимого папки
            prefix = parent_path + '/' if parent_path else ''

            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter='/'
            )

            for page in pages:
                if 'CommonPrefixes' in page:
                    for sub_prefix in page['CommonPrefixes']:
                        sub_path = sub_prefix['Prefix'].rstrip('/')

                        # Пропускаем, если это текущая папка
                        if sub_path == parent_path:
                            continue

                        # Добавляем папку в набор
                        folders_set.add(sub_path)

                        # Рекурсивно получаем подпапки
                        self._get_subfolders(sub_path, folders_set)

        except ClientError as e:
            print(f"Error getting subfolders for {parent_path}: {str(e)}")
