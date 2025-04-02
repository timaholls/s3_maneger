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
from .captcha import Captcha  # <-- Импортируем класс Captcha

from .models import UserPermission, S3ActionLog
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
                    next_url = request.GET.get('next', 's3app:browser')
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


@ensure_csrf_cookie  # <-- ADD THIS DECORATOR
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
def browser_view(request, path=''):
    path = path.rstrip('/')
    s3_service = S3Service()
    search_query = request.GET.get('q', '').strip()  # Keep query separate

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

            paginator = Paginator(all_items, 10)  # Changed to 10 items per page
            page_number = request.GET.get('page')
            context['page_obj'] = paginator.get_page(page_number)

    except PermissionDenied as e:
        messages.error(request, str(e))
        # Redirect to root if permission denied on a subpath, unless already at root
        if path:
            # Decide where to redirect: root or parent? Parent might also be denied. Root is safer.
            return redirect('s3app:browser')
        # If denied at root, just show the error on the root page (handled by template)
    except ClientError as e:
        error_message = f'Ошибка при взаимодействии с S3: {str(e)}'
        # Check for specific S3 errors if needed
        # if e.response['Error']['Code'] == '...':
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
        return redirect('s3app:browser_path', path=path)
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

    # Перенаправляем на страницу просмотра родительской директории
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser_path', path=parent_path)
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
        return redirect('s3app:browser_path', path=path)
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

    # Перенаправляем на страницу просмотра родительской директории
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser_path', path=parent_path)
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

    # Перенаправляем на страницу просмотра родительской директории в случае ошибки
    parent_path = '/'.join(path.split('/')[:-1])
    if parent_path:
        return redirect('s3app:browser_path', path=parent_path)
    else:
        return redirect('s3app:browser')


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
        # Делаем поля пароля необязательными при редактировании
        form.fields['password1'].required = False
        form.fields['password2'].required = False

    return render(request, 'user_form.html', {'form': form, 'title': 'Редактирование пользователя'})


@staff_member_required
def user_permissions(request, user_id):
    """Управление правами доступа пользователя (только для администраторов)"""
    user = get_object_or_404(User, id=user_id)
    permissions = UserPermission.objects.filter(user=user).order_by('folder_path')

    if request.method == 'POST':
        form = UserPermissionForm(request.POST)
        if form.is_valid():
            # Проверяем, существуют ли уже права для этой папки
            folder_path = form.cleaned_data['folder_path']
            existing_perm = UserPermission.objects.filter(user=user, folder_path=folder_path).first()

            if existing_perm:
                # Обновляем существующие права
                existing_perm.can_read = form.cleaned_data['can_read']
                existing_perm.can_write = form.cleaned_data['can_write']
                existing_perm.can_delete = form.cleaned_data['can_delete']
                existing_perm.save()
                messages.success(request, f'Права доступа обновлены для {folder_path}')
            else:
                # Создаем новые права
                perm = form.save(commit=False)
                perm.user = user
                perm.save()
                messages.success(request, f'Права доступа добавлены для {folder_path}')

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
