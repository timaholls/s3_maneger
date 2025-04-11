# s3app/middleware.py
import logging
from django.conf import settings
from django.utils.http import urlencode
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.core.exceptions import PermissionDenied
from django.contrib import messages

logger = logging.getLogger(__name__)


class BrowserChallengeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.cookie_name = settings.BROWSER_CHALLENGE_COOKIE_NAME
        self.cookie_value = settings.BROWSER_CHALLENGE_COOKIE_VALUE
        self.challenge_url = settings.BROWSER_CHALLENGE_URL
        self.validation_url = settings.BROWSER_VALIDATION_URL
        # Пути, которые НЕ нужно проверять
        self.excluded_paths = [
            self.challenge_url,
            self.validation_url,
            settings.STATIC_URL,  # Исключаем статику
            settings.MEDIA_URL if hasattr(settings, 'MEDIA_URL') else None,  # Исключаем медиа
            '/admin/',  # Исключаем админку
            '/login/',  # Exclude login page to prevent redirect loops
        ]
        # Убираем None из списка, если MEDIA_URL не задан
        self.excluded_paths = [p for p in self.excluded_paths if p is not None]

    def __call__(self, request):
        # Проверяем, нужно ли пропускать этот путь
        if any(request.path.startswith(p) for p in self.excluded_paths):
            # logger.debug(f"Skipping challenge for excluded path: {request.path}")
            return self.get_response(request)

        # Проверяем наличие и валидность cookie
        cookie_val = request.COOKIES.get(self.cookie_name)
        if cookie_val == self.cookie_value:
            # logger.debug(f"Browser verified via cookie for path: {request.path}")
            return self.get_response(request)

        # Cookie нет или он невалиден - редирект на страницу проверки
        logger.info(f"Browser challenge required for IP: {self._get_client_ip(request)}, Path: {request.path}")

        # Формируем URL для редиректа, добавляя текущий путь как 'next'
        redirect_url = f"{self.challenge_url}?{urlencode({'next': request.get_full_path()})}"
        return redirect(redirect_url)

    def _get_client_ip(self, request):
        """Получение IP адреса клиента с учетом прокси"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class AdminAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # URL, с которого начинается админ-панель
        self.admin_url_path = getattr(settings, 'ADMIN_URL', '/admin/')
        # Имя URL-паттерна для главной страницы вашего приложения (s3app)
        # Убедитесь, что у вас есть URL-паттерн с name='browser' в s3app/urls.py
        self.redirect_url_name = 's3app:browser'
        # Резервный URL, если reverse не сработает
        self.fallback_redirect_url = '/'

    def __call__(self, request):
        # Проверяем, начинается ли путь запроса с пути к админке
        if request.path.startswith(self.admin_url_path):
            # Проверяем, аутентифицирован ли пользователь и НЕ является ли он staff
            # Анонимные пользователи также не пройдут проверку is_staff
            if not request.user.is_staff:
                # Перенаправляем не-администраторов
                try:
                    # Пытаемся получить URL по имени
                    redirect_url = reverse(self.redirect_url_name)
                except NoReverseMatch:
                    # Если имя не найдено, используем резервный URL
                    redirect_url = self.fallback_redirect_url

                # Выполняем перенаправление
                return redirect(redirect_url)

        # Если это не админка или пользователь является staff,
        # продолжаем обработку запроса как обычно
        response = self.get_response(request)
        return response


class DocumentSignatureCheckMiddleware:
    """Middleware для проверки наличия неподписанных документов и ограничения действий"""
    def __init__(self, get_response):
        self.get_response = get_response
        # Пути, которые НЕ нужно проверять
        self.excluded_paths = [
            '/static/',
            '/media/',
            '/login/',
            '/logout/',
            '/browser-challenge/',
            '/documents-for-signature/',
            '/documents/view/',
            '/documents/sign/',
        ]
        # Пути, для которых нужна проверка документов
        self.checked_actions = [
            '/create-folder/',
            '/delete-folder/',
            '/upload-file/',
            '/delete-file/',
            '/download-file/',
            '/move-file/',
            '/move-folder/',
            '/download-multiple/',
            '/delete-multiple/',
            '/move-multiple/',
        ]

    def __call__(self, request):
        # Проверяем, аутентифицирован ли пользователь
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Суперпользователи освобождены от проверки
        if request.user.is_superuser:
            return self.get_response(request)

        # Проверяем, является ли путь исключенным из проверки
        if any(request.path.startswith(path) for path in self.excluded_paths):
            return self.get_response(request)

        # Проверяем, относится ли путь к действиям, которые нужно проверять
        if any(request.path.startswith(action) for action in self.checked_actions):
            # Импортируем модель здесь, чтобы избежать циклических импортов
            from .models import DocumentSignature

            # Проверяем, есть ли у пользователя неподписанные документы
            if DocumentSignature.has_pending_documents(request.user):
                # Если это AJAX запрос, возвращаем JSON с ошибкой
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({
                        'error': 'Для выполнения этого действия необходимо подписать все документы',
                        'redirect_to': reverse('s3app:documents_for_signature')
                    }, status=403)

                # Для обычных запросов добавляем сообщение и перенаправляем
                messages.warning(
                    request,
                    'Для выполнения этого действия необходимо подписать все документы'
                )
                return redirect('s3app:documents_for_signature')

        return self.get_response(request)
