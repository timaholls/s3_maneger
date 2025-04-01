# s3app/middleware.py
import logging
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

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
            settings.STATIC_URL, # Исключаем статику
            settings.MEDIA_URL if hasattr(settings, 'MEDIA_URL') else None, # Исключаем медиа
            '/admin/', # Исключаем админку
            '/login/', # Exclude login page to prevent redirect loops
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
