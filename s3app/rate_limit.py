import time
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings
from django.utils import timezone
import datetime
import threading
#
class RateLimitMiddleware:
    """
    Middleware для ограничения количества запросов по IP-адресу
    и временной блокировки IP-адресов при превышении лимита
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Настройки по умолчанию (можно переопределить в settings.py)
        self.rate_limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)  # запросов
        self.rate_limit_period = getattr(settings, 'RATE_LIMIT_PERIOD', 60)  # секунд
        self.block_duration = getattr(settings, 'IP_BLOCK_DURATION', 1800)  # 30 минут в секундах
        self.block_threshold = getattr(settings, 'IP_BLOCK_THRESHOLD', 3)  # Количество нарушений перед блокировкой

    def __call__(self, request):
        # Получаем IP пользователя
        ip = self._get_client_ip(request)

        # Пропускаем ограничение для админки и для trusted IPs
        if self._is_exempt(request):
            return self.get_response(request)

        # Проверка, не заблокирован ли IP
        is_blocked, block_info = self._is_ip_blocked(ip)
        if is_blocked:
            remaining_time = int((block_info['expires_at'] - timezone.now()).total_seconds() / 60)
            return HttpResponse(
                f"Ваш IP-адрес временно заблокирован из-за превышения лимита запросов. "
                f"Пожалуйста, повторите попытку через {remaining_time} минут.",
                status=403
            )

        # Проверяем, не превышен ли лимит запросов
        rate_limit_check = self._check_rate_limit(ip)
        if not rate_limit_check['allowed']:
            # Увеличиваем счетчик нарушений
            violation_count = self._increment_violation_count(ip)

            # Если превышен порог нарушений - блокируем IP
            if self._should_block_ip(ip):
                self._block_ip(ip, f"Превышение лимита запросов {violation_count} раз")
                return HttpResponse(
                    f"Ваш IP-адрес заблокирован на {self.block_duration // 60} минут из-за многократного превышения лимита запросов.",
                    status=403
                )
            else:
                return HttpResponse(
                    f"Превышен лимит запросов ({self.rate_limit} запросов за {self.rate_limit_period} секунд). "
                    f"Пожалуйста, подождите {rate_limit_check['reset_in']} секунд.",
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

    def _is_exempt(self, request):
        """Проверка, освобожден ли запрос от ограничений"""
        # Пропускаем админку
        if request.path.startswith('/admin/'):
            return True

        # Проверка доверенных IP (если настроено)
        trusted_ips = getattr(settings, 'TRUSTED_IPS', [])
        client_ip = self._get_client_ip(request)
        if client_ip in trusted_ips:
            return True

        return False

    def _check_rate_limit(self, ip):
        """Проверка ограничения количества запросов"""
        cache_key = f"rate_limit:{ip}"

        # Получаем текущее состояние счетчика
        requests = cache.get(cache_key, [])

        # Текущее время
        now = time.time()

        # Удаляем запросы старше периода ограничения
        requests = [req_time for req_time in requests if now - req_time < self.rate_limit_period]

        # Если лимит достигнут, вычисляем время до сброса
        if len(requests) >= self.rate_limit:
            oldest_request = min(requests) if requests else now
            reset_in = int(self.rate_limit_period - (now - oldest_request))
            return {
                'allowed': False,
                'count': len(requests),
                'limit': self.rate_limit,
                'reset_in': reset_in
            }

        # Добавляем текущий запрос
        requests.append(now)

        # Обновляем кэш
        cache.set(cache_key, requests, self.rate_limit_period * 2)

        return {
            'allowed': True,
            'count': len(requests),
            'limit': self.rate_limit,
            'reset_in': self.rate_limit_period
        }

    def _increment_violation_count(self, ip):
        """Увеличивает счетчик нарушений для IP"""
        cache_key = f"violation_count:{ip}"
        count = cache.get(cache_key, 0)
        count += 1
        # Храним счетчик нарушений на протяжении 1 часа
        cache.set(cache_key, count, 3600)
        return count

    def _should_block_ip(self, ip):
        """Проверяет, нужно ли блокировать IP на основе количества нарушений"""
        cache_key = f"violation_count:{ip}"
        count = cache.get(cache_key, 0)
        return count >= self.block_threshold

    def _block_ip(self, ip, reason="Превышение лимита запросов"):
        """Блокирует IP на указанный период времени и сохраняет в БД"""
        now = timezone.now()
        expires_at = now + datetime.timedelta(seconds=self.block_duration)

        # Сохраняем в кэше для быстрого доступа
        cache_key = f"ip_blocked:{ip}"
        cache.set(cache_key, {
            'blocked_at': now,
            'expires_at': expires_at,
            'reason': reason
        }, self.block_duration)

        # Асинхронно сохраняем в БД
        self._save_block_to_db(ip, now, expires_at, reason)

        return True

    def _save_block_to_db(self, ip, blocked_at, expires_at, reason):
        """Сохраняет блокировку в базе данных в отдельном потоке"""
        def _save_block():
            try:
                from django.apps import apps
                IPBlock = apps.get_model('s3app', 'IPBlock')

                # Проверяем, существует ли уже активная блокировка
                existing_block = IPBlock.objects.filter(
                    ip_address=ip,
                    is_active=True
                ).first()

                if existing_block:
                    # Обновляем существующую блокировку
                    existing_block.expires_at = expires_at
                    existing_block.reason = reason
                    existing_block.save()
                else:
                    # Создаем новую блокировку
                    IPBlock.objects.create(
                        ip_address=ip,
                        blocked_at=blocked_at,
                        expires_at=expires_at,
                        reason=reason,
                        is_active=True
                    )
            except Exception as e:
                # Логируем ошибку, но не прерываем выполнение
                self._log_error(f"Ошибка при сохранении блокировки IP в БД: {str(e)}")

        # Запускаем в отдельном потоке, чтобы не блокировать запрос
        thread = threading.Thread(target=_save_block)
        thread.daemon = True
        thread.start()

    def _is_ip_blocked(self, ip):
        """Проверяет, заблокирован ли IP"""
        # Сначала проверяем кэш для быстрого ответа
        cache_key = f"ip_blocked:{ip}"
        block_info = cache.get(cache_key)

        if block_info:
            # Проверяем, не истекла ли блокировка
            if block_info['expires_at'] < timezone.now():
                cache.delete(cache_key)
                return False, None
            return True, block_info

        # Если в кэше нет, проверяем БД
        try:
            from django.apps import apps
            IPBlock = apps.get_model('s3app', 'IPBlock')

            block = IPBlock.objects.filter(
                ip_address=ip,
                is_active=True,
                expires_at__gt=timezone.now()
            ).first()

            if block:
                # Добавляем в кэш для ускорения будущих проверок
                cache_data = {
                    'blocked_at': block.blocked_at,
                    'expires_at': block.expires_at,
                    'reason': block.reason
                }

                # Вычисляем оставшееся время блокировки в секундах
                remaining_seconds = int((block.expires_at - timezone.now()).total_seconds())
                cache.set(cache_key, cache_data, remaining_seconds)

                return True, cache_data
        except Exception as e:
            self._log_error(f"Ошибка при проверке блокировки IP в БД: {str(e)}")

        return False, None

    def _log_ip_block(self, ip, blocked_at, expires_at):
        """
        Логирует информацию о блокировке IP
        В боевом окружении здесь можно добавить запись в БД или отправку уведомлений
        """
        try:
            from django.utils.log import logger
            logger.warning(
                f"IP {ip} заблокирован с {blocked_at} до {expires_at} "
                f"за превышение лимита запросов {self.block_threshold} раз"
            )
        except ImportError:
            pass

    def _log_error(self, message):
        """Логирует ошибки middleware"""
        try:
            from django.utils.log import logger
            logger.error(message)
        except ImportError:
            print(message)  # Fallback to console
