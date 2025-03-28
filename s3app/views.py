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

from .models import UserPermission, S3ActionLog
from .forms import (
    LoginForm, CreateFolderForm, UploadFileForm,
    UserPermissionForm, UserCreationForm
)
from .s3_service import S3Service


def login_view(request):
    """Авторизация пользователя"""
    if request.user.is_authenticated:
        return redirect('s3app:browser')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                # Получаем URL для перенаправления после авторизации
                next_url = request.GET.get('next', 's3app:browser')
                messages.success(request, f'Добро пожаловать, {username}!')
                return redirect(next_url)
            else:
                messages.error(request, 'Неверное имя пользователя или пароль.')
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    """Выход пользователя из системы"""
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы.')
    return redirect('s3app:login')


@login_required
def browser_view(request, path=''):
    path = path.rstrip('/')
    s3_service = S3Service()

    context = {
        'current_path': path,
        'parent_path': '/'.join(path.split('/')[:-1]) if path else None,
        'breadcrumbs': _get_breadcrumbs(path),
        'folder_form': CreateFolderForm(),
        'upload_form': UploadFileForm(),
    }

    try:
        import os

        search_query = request.GET.get('q', '').strip().lower()
        result = s3_service.list_objects(request.user, path, delimiter=None)

        # Убедимся, что имя файла — это basename
        for f in result['files']:
            f['name'] = os.path.basename(f['name'])

        if search_query:
            result['files'] = [f for f in result['files'] if search_query in f['name'].lower()]
            result['directories'] = [d for d in result['directories'] if search_query in d['name'].lower()]

        from django.core.paginator import Paginator
        all_items = result['directories'] + result['files']
        paginator = Paginator(all_items, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['page_obj'] = page_obj
        context['search_query'] = search_query

    except PermissionDenied as e:
        messages.error(request, str(e))
        if path:
            return redirect('s3app:browser')
    except ClientError as e:
        messages.error(request, f'Ошибка при получении списка объектов: {str(e)}')

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
            user = form.save()
            messages.success(request, f'Пользователь {user.username} успешно создан')
            return redirect('s3app:user_list')
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
    """Просмотр журнала действий пользователей (только для администраторов)"""
    logs = S3ActionLog.objects.all().order_by('-timestamp')[:1000]  # Ограничиваем вывод 1000 последними записями

    return render(request, 'action_logs.html', {'logs': logs})


def _get_breadcrumbs(path):
    """Вспомогательная функция для формирования хлебных крошек"""
    if not path:
        return []

    breadcrumbs = [{'name': 'Корень', 'path': ''}]
    parts = path.split('/')

    current_path = ''
    for part in parts:
        if part:
            current_path = f"{current_path}/{part}" if current_path else part
            breadcrumbs.append({
                'name': part,
                'path': current_path
            })

    return breadcrumbs
