import time
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings

class RateLimitMiddleware:
    """
    Middleware для ограничения количества запросов по IP-адресу
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Настройки по умолчанию (можно переопределить в settings.py)
        self.rate_limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)  # запросов
        self.rate_limit_period = getattr(settings, 'RATE_LIMIT_PERIOD', 60)  # секунд

    def __call__(self, request):
        # Получаем IP пользователя
        ip = self._get_client_ip(request)

        # Пропускаем ограничение для админки
        if request.path.startswith('/admin/'):
            return self.get_response(request)

        # Проверяем, не превышен ли лимит запросов
        if not self._check_rate_limit(ip):
            return HttpResponse(
                "Превышен лимит запросов. Пожалуйста, попробуйте позже.",
                status=429
            )

        return self.get_response(request)

    def _get_client_ip(self, request):
        """Получение IP адреса клиента с учетом прокси"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _check_rate_limit(self, ip):
        """Проверка ограничения количества запросов"""
        cache_key = f"rate_limit:{ip}"

        # Получаем текущее состояние счетчика
        requests = cache.get(cache_key, [])

        # Текущее время
        now = time.time()

        # Удаляем запросы старше периода ограничения
        requests = [req_time for req_time in requests if now - req_time < self.rate_limit_period]

        # Слишком много запросов?
        if len(requests) >= self.rate_limit:
            return False

        # Добавляем текущий запрос
        requests.append(now)

        # Обновляем кэш
        cache.set(cache_key, requests, self.rate_limit_period * 2)

        return True
