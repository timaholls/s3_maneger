import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from botocore.exceptions import ClientError
from django import forms
from .forms import LoginForm  # ... другие формы ...
from .captcha import Captcha  # Импортируем класс Captcha

from .models import UserPermission, S3ActionLog, TrashItem
from .forms import (
    LoginForm, CreateFolderForm, UploadFileForm,
    UserPermissionForm, UserCreationForm
)
from .s3_service import S3Service

from django.conf import settings
from django.http import HttpResponse, JsonResponse  # Добавляем JsonResponse
from django.shortcuts import render, redirect  # Убедитесь, что render импортирован
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect  # Для CSRF
from django.views.decorators.http import require_http_methods  # Для ограничения методов
from django.shortcuts import render
from django.core.paginator import Paginator

def login_view(request):
    """Авторизация пользователя с CAPTCHA"""
    if request.user.is_authenticated:
        # Перенаправляем авторизованного пользователя на доступную ему папку
        return redirect('s3app:browser')

    captcha_data = None  # Инициализируем

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user_captcha = form.cleaned_data['captcha_input']

            # --- ПРОВЕРКА CAPTCHA ---
            stored_captcha = request.session.get('captcha_text')
            # Удаляем CAPTCHA из сессии после попытки, чтобы предотвратить повторное использование
            request.session.pop('captcha_text', None)

            if Captcha.verify_captcha(user_captcha, stored_captcha):
                # CAPTCHA верна, пытаемся аутентифицировать
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    # Получаем параметр next из URL или используем маршрут на redirect_after_login
                    next_url = request.GET.get('next', 'none')

                    # Если next не задан явно, определяем первую доступную папку
                    if next_url == 'none':
                        messages.success(request, f'Добро пожаловать, {username}!')
                        return redirect('s3app:redirect_after_login')
                    else:
                        messages.success(request, f'Добро пожаловать, {username}!')
                        return redirect(next_url)
                else:
                    messages.error(request, 'Неверное имя пользователя или пароль.')
                    # Генерируем новую CAPTCHA для следующей попытки
                    captcha_data = Captcha.generate_captcha()
                    request.session['captcha_text'] = captcha_data['captcha_text']
            else:
                # CAPTCHA неверна
                messages.error(request, 'Неверный текст с картинки (CAPTCHA).')
                # Генерируем новую CAPTCHA для следующей попытки
                captcha_data = Captcha.generate_captcha()
                request.session['captcha_text'] = captcha_data['captcha_text']
        else:
            # Форма невалидна (например, не заполнено поле)
            # Генерируем новую CAPTCHA, т.к. страница будет перерисована
            captcha_data = Captcha.generate_captcha()
            request.session['captcha_text'] = captcha_data['captcha_text']

    else:  # GET запрос
        form = LoginForm()
        # Генерируем CAPTCHA для отображения на странице
        captcha_data = Captcha.generate_captcha()
        request.session['captcha_text'] = captcha_data['captcha_text']

    # Передаем данные CAPTCHA в контекст (изображение нужно только для GET или при ошибке POST)
    context = {
        'form': form,
        'captcha_image': captcha_data['captcha_image'] if captcha_data else None
    }
    return render(request, 'login.html', context)


def logout_view(request):
    """Выход пользователя из системы"""
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы.')
    return redirect('s3app:login')


@ensure_csrf_cookie  # Устанавливает CSRF cookie, чтобы JS мог его прочитать
def browser_challenge_page_view(request):
    """Отображает страницу проверки браузера."""
    # Добавим next_url в контекст, чтобы его можно было использовать в шаблоне
    next_url = request.GET.get('next', '/manager/')
    return render(request, 'browser_challenge.html', {'next_url': next_url})


@ensure_csrf_cookie  # ADD THIS DECORATOR
@csrf_protect  # Требует валидный CSRF токен для POST
@require_http_methods(["POST"])  # Разрешаем только POST
def browser_challenge_validate_view(request):
    """Обрабатывает AJAX-запрос от JS и устанавливает cookie."""
    import json
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Логирование для отладки
        logger.info(f"Browser challenge validation request received from {request.META.get('REMOTE_ADDR')}")

        # Проверка данных запроса
        try:
            data = json.loads(request.body)
            logger.info(f"Received data: {data}")
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in request body")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Создаем успешный ответ
        response = JsonResponse({'status': 'success'})

        # Устанавливаем cookie
        cookie_name = settings.BROWSER_CHALLENGE_COOKIE_NAME
        cookie_value = settings.BROWSER_CHALLENGE_COOKIE_VALUE
        cookie_age = settings.BROWSER_CHALLENGE_COOKIE_AGE

        logger.info(f"Setting cookie: {cookie_name}={cookie_value} (max_age={cookie_age})")

        response.set_cookie(
            key=cookie_name,
            value=cookie_value,
            max_age=cookie_age,
            secure=request.is_secure(),  # True, если HTTPS
            httponly=False,  # Доступен для JS для отладки
            samesite='Lax'  # Защита от CSRF для cookie
        )

        # Добавляем заголовки для отладки
        response['X-Browser-Challenge'] = 'passed'

        logger.info("Browser challenge validation successful")
        return response

    except Exception as e:
        logger.exception(f"Browser challenge validation error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def redirect_after_login(request):
    """Перенаправляет пользователя после входа на первую доступную ему папку"""
    user = request.user

    # Для суперпользователей сразу перенаправляем в корень
    if user.is_superuser:
        return redirect('s3app:browser')

    # Получаем все права доступа пользователя
    permissions = UserPermission.objects.filter(user=user, can_read=True).order_by('folder_path')

    # Проверяем, есть ли права на чтение корневой директории
    root_permission = permissions.filter(folder_path='').first()
    if root_permission and root_permission.can_read:
        return redirect('s3app:browser')

    # Ищем первую доступную папку
    for permission in permissions:
        if permission.folder_path:  # Пропускаем пустой путь (корень)
            # Перенаправляем на первую доступную папку
            return redirect('s3app:browser', path=permission.folder_path)

    # Если не нашли ни одной доступной папки, перенаправляем в корень с вероятным сообщением об ошибке
    # S3Service в browser_view покажет сообщение об ошибке доступа
    return redirect('s3app:browser')


@login_required
def browser_view(request, path=''):
    path = path.rstrip('/')
    s3_service = S3Service()
    search_query = request.GET.get('q', '').strip()  # Keep query separate

    # Получаем количество элементов на странице из GET-параметра или используем значение по умолчанию
    try:
        items_per_page = int(request.GET.get('per_page', 10))
        # Проверка на допустимые значения
        if items_per_page not in [10, 20, 50, 100]:
            items_per_page = 10
    except ValueError:
        items_per_page = 10

    context = {
        'current_path': path,
        'parent_path': '/'.join(path.split('/')[:-1]) if path else None,
        'breadcrumbs': _get_breadcrumbs(path),
        'folder_form': CreateFolderForm(),
        'upload_form': UploadFileForm(),
        'search_query': search_query,  # Pass search query to template
        'is_search_view': bool(search_query),  # Flag for template
        'search_results': [],  # Initialize search results list
        'page_obj': None,  # Initialize page_obj
        'items_per_page': items_per_page,  # Добавляем в контекст количество элементов на странице
    }

    try:
        if search_query:
            # --- SEARCH LOGIC ---
            context['search_results'] = s3_service.search_objects(
                request.user,
                prefix=path,
                query=search_query,
                max_results=200  # Limit the number of search results shown
            )
            if not context['search_results']:
                messages.info(request,
                              f"Файлы, содержащие '{search_query}', не найдены в '{path or 'Корневой директории'}' и подпапках.")

        else:
            # --- BROWSE LOGIC ---
            result = s3_service.list_objects(request.user, path)  # Standard listing

            # Combine directories and files for pagination
            all_items = result['directories'] + result['files']

            from django.core.paginator import Paginator  # Keep Paginator import

            paginator = Paginator(all_items, items_per_page)  # Используем динамическое количество элементов на странице
            page_number = request.GET.get('page')
            context['page_obj'] = paginator.get_page(page_number)

    except PermissionDenied as e:
        messages.error(request, str(e))
        # Если нет прав, перенаправляем на первую доступную директорию или оставляем на текущей странице
        if path:
            # Редирект на страницу определения первой доступной директории
            return redirect('s3app:redirect_after_login')
    except ClientError as e:
        error_message = f'Ошибка при взаимодействии с S3: {str(e)}'
        # Check for specific S3 errors if needed
        # if e.response['Error']['Code'] == '...'
        messages.error(request, error_message)
        # Log the detailed error for admin/debugging
        print(f"S3 ClientError in browser_view (path: {path}, query: {search_query}): {e}")

    return render(request, 'browser.html', context)


@login_required
def create_folder(request, path=''):
    if path == "root":
        path = ""
    """Создание новой папки в указанном пути"""
    if request.method == 'POST':
        form = CreateFolderForm(request.POST)
        if form.is_valid():
            folder_name = form.cleaned_data['folder_name']

            # Формируем полный путь к новой папке
            if path:
                new_folder_path = f"{path}/{folder_name}"
            else:
                new_folder_path = folder_name

            try:
                # Создаем новую папку в S3
                s3_service = S3Service()
                result = s3_service.create_folder(request.user, new_folder_path)
                messages.success(request, result['message'])
            except PermissionDenied as e:
                messages.error(request, str(e))
            except ClientError as e:
                messages.error(request, f'Ошибка при создании папки: {str(e)}')

    # Перенаправляем на страницу просмотра текущей директории
    if path:
        return redirect('s3app:browser', path=path)
    else:
        return redirect('s3app:browser')


@login_required
def delete_folder(request, path):
    """Удаление папки из S3"""
    if not path:
        messages.error(request, 'Невозможно удалить корневую директорию')
        return redirect('s3app:browser')

    try:
        # Удаляем папку из S3
        s3_service = S3Service()
        result = s3_service.delete_folder(request.user, path)
        messages.success(request, result['message'])
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ClientError as e:
        messages.error(request, f'Ошибка при удалении папки: {str(e)}')

    # Перенаправляем на родительскую директорию
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser', path=parent_path)
    else:
        return redirect('s3app:browser')


@login_required
def upload_file(request, path=''):
    if path == "root":
        path = ""
    """Загрузка файла в указанный путь"""
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            file_obj = request.FILES['file']
            filename = file_obj.name

            # Формируем полный путь для загрузки файла
            if path:
                destination_path = f"{path}/{filename}"
            else:
                destination_path = filename

            try:
                # Загружаем файл в S3
                s3_service = S3Service()
                result = s3_service.upload_file(request.user, file_obj, destination_path)
                messages.success(request, result['message'])
            except PermissionDenied as e:
                messages.error(request, str(e))
            except ClientError as e:
                messages.error(request, f'Ошибка при загрузке файла: {str(e)}')

    # Перенаправляем на страницу просмотра текущей директории
    if path:
        return redirect('s3app:browser', path=path)
    else:
        return redirect('s3app:browser')


@login_required
def delete_file(request, path):
    """Удаление файла из S3"""
    if not path:
        messages.error(request, 'Невозможно удалить файл: некорректный путь')
        return redirect('s3app:browser')

    try:
        # Удаляем файл из S3
        s3_service = S3Service()
        result = s3_service.delete_file(request.user, path)
        messages.success(request, result['message'])
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ClientError as e:
        messages.error(request, f'Ошибка при удалении файла: {str(e)}')

    # Перенаправляем на родительскую директорию
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser', path=parent_path)
    else:
        return redirect('s3app:browser')


@login_required
def download_file(request, path):
    """Скачивание файла из S3"""
    if not path:
        messages.error(request, 'Невозможно скачать файл: некорректный путь')
        return redirect('s3app:browser')

    try:
        # Генерируем временную ссылку для скачивания файла
        s3_service = S3Service()
        result = s3_service.generate_download_url(request.user, path)

        # Перенаправляем пользователя на временную ссылку для скачивания
        return redirect(result['url'])
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ClientError as e:
        messages.error(request, f'Ошибка при скачивании файла: {str(e)}')

    # Перенаправляем на родительскую директорию в случае ошибки
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser', path=parent_path)
    else:
        return redirect('s3app:browser')


@login_required
def move_file(request, path):
    """Перемещение файла в другую папку"""
    if not path:
        messages.error(request, 'Невозможно переместить файл: некорректный путь')
        return redirect('s3app:browser')

    if request.method == 'POST':
        destination_folder = request.POST.get('destination_folder', '').strip()

        try:
            # Перемещаем файл в другую папку
            s3_service = S3Service()
            result = s3_service.move_object(request.user, path, destination_folder, is_folder=False)
            messages.success(request, result['message'])
        except PermissionDenied as e:
            messages.error(request, str(e))
        except ClientError as e:
            messages.error(request, f'Ошибка при перемещении файла: {str(e)}')

    # Перенаправляем на родительскую директорию
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser', path=parent_path)
    else:
        return redirect('s3app:browser')


@login_required
def move_folder(request, path):
    """Перемещение папки в другую папку"""
    if not path:
        messages.error(request, 'Невозможно переместить корневую директорию')
        return redirect('s3app:browser')

    if request.method == 'POST':
        destination_folder = request.POST.get('destination_folder', '').strip()

        # Проверка, чтобы не перемещать папку в саму себя или свою подпапку
        if destination_folder.startswith(path) or destination_folder == path:
            messages.error(request, 'Невозможно переместить папку внутрь самой себя или в свою подпапку')
            return redirect('s3app:browser', path=path)

        try:
            # Перемещаем папку в другую папку
            s3_service = S3Service()
            result = s3_service.move_object(request.user, path, destination_folder, is_folder=True)
            messages.success(request, result['message'])
        except PermissionDenied as e:
            messages.error(request, str(e))
        except ClientError as e:
            messages.error(request, f'Ошибка при перемещении папки: {str(e)}')

    # Перенаправляем на родительскую директорию
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser', path=parent_path)
    else:
        return redirect('s3app:browser')


@login_required
@require_http_methods(["POST"])
def move_multiple(request):
    """Обработчик для перемещения нескольких файлов и/или папок"""
    # Получаем списки файлов и папок для перемещения
    file_paths = request.POST.getlist('files[]')
    folder_paths = request.POST.getlist('folders[]')
    destination_folder = request.POST.get('destination_folder', '').strip()

    if not file_paths and not folder_paths:
        return JsonResponse({'error': 'No items selected'}, status=400)

    if not destination_folder and destination_folder != '':
        return JsonResponse({'error': 'No destination folder specified'}, status=400)

    s3_service = S3Service()

    # Счетчики успешных операций
    moved_files = 0
    moved_folders = 0
    errors = []

    # Перемещаем файлы
    for file_path in file_paths:
        try:
            s3_service.move_object(request.user, file_path, destination_folder, is_folder=False)
            moved_files += 1
        except Exception as e:
            errors.append(f"Не удалось переместить файл {file_path}: {str(e)}")

    # Перемещаем папки
    for folder_path in folder_paths:
        # Проверка, чтобы не перемещать папку в саму себя или свою подпапку
        if destination_folder.startswith(folder_path) or destination_folder == folder_path:
            errors.append(f"Невозможно переместить папку {folder_path} внутрь самой себя или в свою подпапку")
            continue

        try:
            s3_service.move_object(request.user, folder_path, destination_folder, is_folder=True)
            moved_folders += 1
        except Exception as e:
            errors.append(f"Не удалось переместить папку {folder_path}: {str(e)}")

    response_data = {
        'success': True,
        'moved_files': moved_files,
        'moved_folders': moved_folders,
        'errors': errors
    }

    return JsonResponse(response_data)


@staff_member_required
def user_list(request):
    """Список пользователей (только для администраторов)"""
    users = User.objects.all().order_by('username')

    return render(request, 'user_list.html', {'users': users})


@staff_member_required
def user_create(request):
    """Создание нового пользователя (только для администраторов)"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()  # This saves the user with hashed password

            # --- START: ADD DEFAULT PERMISSION ---
            if user:  # Check if user was created successfully
                try:
                    UserPermission.objects.create(
                        user=user,
                        folder_path='',  # Empty string represents the root directory
                        can_read=True,  # Grant read access
                        can_write=False,  # Explicitly deny write access by default
                        can_delete=False  # Explicitly deny delete access by default
                    )
                    messages.success(request, f'Пользователь {user.username} успешно создан.')
                    messages.info(request,
                                  f'Пользователю {user.username} предоставлены права на чтение/скачивание по умолчанию для всего хранилища.')
                except Exception as e:
                    # Handle potential errors during permission creation (e.g., database issues)
                    messages.error(request,
                                   f'Пользователь {user.username} создан, но произошла ошибка при назначении прав по умолчанию: {e}')
                    # Optionally delete the user if default permission fails? Or just log it.
                    # user.delete() # Uncomment if you want user creation to be atomic with permission creation
            # --- END: ADD DEFAULT PERMISSION ---

            return redirect('s3app:user_list')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = UserCreationForm()

    return render(request, 'user_form.html', {'form': form, 'title': 'Создание пользователя'})


@staff_member_required
def user_edit(request, user_id):
    """Редактирование пользователя (только для администраторов)"""
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = UserCreationForm(request.POST, instance=user)
        if form.is_valid():
            # Проверяем, был ли введен новый пароль
            if form.cleaned_data.get('password1'):
                user = form.save()
            else:
                # Если пароль не вводился, сохраняем только другие поля
                user = form.save(commit=False)
                user.username = form.cleaned_data['username']
                user.email = form.cleaned_data['email']
                user.first_name = form.cleaned_data['first_name']
                user.last_name = form.cleaned_data['last_name']
                user.is_active = form.cleaned_data['is_active']
                user.save()

            messages.success(request, f'Пользователь {user.username} успешно обновлен')
            return redirect('s3app:user_list')
    else:
        form = UserCreationForm(instance=user)

    return render(request, 'user_form.html', {'form': form, 'title': 'Редактирование пользователя'})


@staff_member_required
def user_permissions(request, user_id):
    """Управление правами доступа пользователя (только для администраторов)"""
    user = get_object_or_404(User, id=user_id)
    permissions = UserPermission.objects.filter(user=user).order_by('folder_path')

    if request.method == 'POST':
        form = UserPermissionForm(request.POST)
        # Получаем список путей из запроса - jQuery отправляет массив как folder_paths[]
        folder_paths = request.POST.getlist('folder_paths[]')

        # Если нет путей, добавляем корневой путь
        if not folder_paths:
            folder_paths = ['']

        if form.is_valid():
            # Общие права для всех путей
            can_read = form.cleaned_data['can_read']
            can_write = form.cleaned_data['can_write']
            can_delete = form.cleaned_data['can_delete']
            can_move = form.cleaned_data['can_move']

            added_paths = []
            updated_paths = []

            # Обрабатываем каждый путь отдельно
            for folder_path in folder_paths:
                # Нормализуем путь
                folder_path = folder_path.strip()

                # Проверяем, существуют ли уже права для этой папки
                existing_perm = UserPermission.objects.filter(user=user, folder_path=folder_path).first()

                if existing_perm:
                    # Обновляем существующие права
                    existing_perm.can_read = can_read
                    existing_perm.can_write = can_write
                    existing_perm.can_delete = can_delete
                    existing_perm.can_move = can_move
                    existing_perm.save()
                    updated_paths.append(folder_path or '(корень)')
                else:
                    # Создаем новые права
                    UserPermission.objects.create(
                        user=user,
                        folder_path=folder_path,
                        can_read=can_read,
                        can_write=can_write,
                        can_delete=can_delete,
                        can_move=can_move
                    )
                    added_paths.append(folder_path or '(корень)')

            # Формируем сообщения
            if added_paths:
                messages.success(request, f'Добавлены права доступа для папок: {", ".join(added_paths)}')

            if updated_paths:
                messages.success(request, f'Обновлены права доступа для папок: {", ".join(updated_paths)}')

            return redirect('s3app:user_permissions', user_id=user.id)
    else:
        form = UserPermissionForm(initial={'user': user})
        form.fields['user'].widget = forms.HiddenInput()

    context = {
        'user_obj': user,
        'permissions': permissions,
        'form': form
    }

    return render(request, 'user_permissions.html', context)


@staff_member_required
def delete_permission(request, perm_id):
    """Удаление права доступа (только для администраторов)"""
    perm = get_object_or_404(UserPermission, id=perm_id)
    user_id = perm.user.id
    folder_path = perm.folder_path

    perm.delete()
    messages.success(request, f'Права доступа для {folder_path} удалены')

    return redirect('s3app:user_permissions', user_id=user_id)


@staff_member_required
def action_logs(request):
    # Get all logs, ordered by timestamp (newest first is common)
    log_list = S3ActionLog.objects.all().order_by('-timestamp')

    # Set up Paginator
    paginator = Paginator(log_list, 20) # 20 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number) # Get the Page object for the current page

    context = {
        'page_obj': page_obj # Pass the Page object to the template
    }
    return render(request, 'action_logs.html', context)


@login_required
@require_http_methods(["POST"])
def download_multiple(request):
    """Обработчик для скачивания нескольких файлов в виде ZIP-архива"""
    import zipfile
    import io
    import tempfile
    import time

    # Получаем список файлов для скачивания
    file_paths = request.POST.getlist('files[]')

    if not file_paths:
        return JsonResponse({'error': 'No files selected'}, status=400)

    # Создаем временный архив
    s3_service = S3Service()

    try:
        # Используем временный файл вместо памяти для больших архивов
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
            temp_file_path = temp_file.name

        with zipfile.ZipFile(temp_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in file_paths:
                try:
                    # Получаем файл из S3
                    file_content = s3_service.get_object_content(request.user, file_path)

                    # Добавляем файл в архив с только именем файла (без пути)
                    zip_file.writestr(os.path.basename(file_path), file_content)

                    # Логируем действие
                    S3ActionLog.objects.create(
                        user=request.user,
                        action='download',
                        path=file_path,
                        details=f'Downloaded in bulk archive'
                    )
                except Exception as e:
                    # Пропускаем файлы, которые не удалось скачать
                    continue

        # Открываем архив для отправки
        with open(temp_file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="files_{int(time.time())}.zip"'

        # Удаляем временный файл
        os.unlink(temp_file_path)

        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def delete_multiple(request):
    """Обработчик для удаления нескольких файлов и/или папок"""
    # Получаем списки файлов и папок для удаления
    file_paths = request.POST.getlist('files[]')
    folder_paths = request.POST.getlist('folders[]')

    if not file_paths and not folder_paths:
        return JsonResponse({'error': 'No items selected'}, status=400)

    s3_service = S3Service()

    # Счетчики успешных операций
    deleted_files = 0
    deleted_folders = 0
    errors = []

    # Удаляем файлы
    for file_path in file_paths:
        try:
            s3_service.delete_object(request.user, file_path)
            deleted_files += 1

            # Логируем действие
            S3ActionLog.objects.create(
                user=request.user,
                action='delete',
                path=file_path,
                details=f'Deleted in bulk operation'
            )
        except Exception as e:
            errors.append(f"Не удалось удалить файл {file_path}: {str(e)}")

    # Удаляем папки
    for folder_path in folder_paths:
        try:
            s3_service.delete_folder(request.user, folder_path)
            deleted_folders += 1

            # Логируем действие
            S3ActionLog.objects.create(
                user=request.user,
                action='delete',
                path=folder_path,
                details=f'Deleted folder in bulk operation'
            )
        except Exception as e:
            errors.append(f"Не удалось удалить папку {folder_path}: {str(e)}")

    response_data = {
        'success': True,
        'deleted_files': deleted_files,
        'deleted_folders': deleted_folders,
        'errors': errors
    }

    return JsonResponse(response_data)


@staff_member_required
def folders_autocomplete(request):
    """AJAX обработчик для автозаполнения путей папок"""
    term = request.GET.get('term', '').strip()

    if not term or len(term) < 2:
        return JsonResponse([], safe=False)

    s3_service = S3Service()

    try:
        # Получаем все папки
        all_folders = s3_service.list_all_folders()

        # Фильтруем их по поисковому запросу (регистронезависимо)
        term_lower = term.lower()
        matching_folders = [folder for folder in all_folders if term_lower in folder.lower()]

        # Ограничиваем количество результатов
        matching_folders = matching_folders[:10]

        return JsonResponse(matching_folders, safe=False)

    except Exception as e:
        # В случае ошибки возвращаем пустой список
        print(f"Error in folders_autocomplete: {str(e)}")
        return JsonResponse([], safe=False)


@staff_member_required
def trash_view(request):
    """Просмотр корзины (только для администраторов)"""
    s3_service = S3Service()

    # Получаем список элементов в корзине
    trash_items = s3_service.list_trash_items()

    # Пагинация
    paginator = Paginator(trash_items, 20)  # 20 элементов на странице
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'trash_items': page_obj,  # Для совместимости с шаблоном
    }

    return render(request, 'trash.html', context)

@staff_member_required
def restore_from_trash(request, item_id):
    """Восстановление элемента из корзины (только для администраторов)"""
    s3_service = S3Service()

    # Восстанавливаем элемент
    result = s3_service.restore_from_trash(request.user, item_id)

    if result['success']:
        messages.success(request, result['message'])
    else:
        messages.error(request, result['message'])

    return redirect('s3app:trash')

@staff_member_required
def delete_from_trash(request, item_id):
    """Окончательное удаление элемента из корзины (только для администраторов)"""
    s3_service = S3Service()

    # Удаляем элемент из корзины
    result = s3_service.delete_from_trash(item_id)

    if result['success']:
        messages.success(request, result['message'])
    else:
        messages.error(request, result['message'])

    return redirect('s3app:trash')

@staff_member_required
def empty_trash(request):
    """Полная очистка корзины (только для администраторов)"""
    if request.method != 'POST':
        messages.error(request, "Метод не поддерживается")
        return redirect('s3app:trash')

    s3_service = S3Service()

    # Очищаем корзину
    result = s3_service.empty_trash()

    if result['success']:
        messages.success(request, result['message'])
    else:
        messages.error(request, result['message'])

    return redirect('s3app:trash')

@staff_member_required
def cleanup_expired_trash(request):
    """Очистка элементов корзины с истекшим сроком хранения (только для администраторов)"""
    if request.method != 'POST':
        messages.error(request, "Метод не поддерживается")
        return redirect('s3app:trash')

    s3_service = S3Service()

    # Очищаем элементы с истекшим сроком хранения
    result = s3_service.cleanup_expired_trash()

    if result['success']:
        messages.success(request, result['message'])
    else:
        messages.error(request, result['message'])

    return redirect('s3app:trash')

def _get_breadcrumbs(path):
    """Вспомогательная функция для формирования хлебных крошек"""
    if not path:
        return []

    breadcrumbs = [{'name': 'Корень', 'path': ''}]
    # Ensure splitting handles multiple slashes correctly if _normalize_path didn't catch all
    parts = list(filter(None, path.split('/')))

    current_path = ''
    for part in parts:
        # current_path = f"{current_path}/{part}" if current_path else part
        current_path = os.path.join(current_path, part)  # Safer path joining
        breadcrumbs.append({
            'name': part,
            'path': current_path
        })

    return breadcrumbs
