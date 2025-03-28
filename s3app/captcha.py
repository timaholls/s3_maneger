import random
import string
import base64
import io
import logging
from PIL import Image, ImageDraw, ImageFont
from django.utils.crypto import get_random_string

logger = logging.getLogger(__name__)

class Captcha:
    """
    Класс для генерации и проверки CAPTCHA
    """
    @staticmethod
    def generate_captcha_text(length=5):
        """Генерация случайного текста для CAPTCHA"""
        # Используем только буквы и цифры, которые сложно перепутать
        chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
        captcha_text = ''.join(random.choice(chars) for _ in range(length))
        logger.info(f"Generated CAPTCHA text: {captcha_text}")
        return captcha_text

    @staticmethod
    def generate_captcha_image(text, width=280, height=100):
        """Генерация простого изображения CAPTCHA с более крупными символами"""
        # Создаем изображение с белым фоном
        image = Image.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)

        # Добавляем цветной фон
        for y in range(height):
            for x in range(width):
                # Создаем случайный светлый цвет для фона
                color = (
                    random.randint(220, 255),
                    random.randint(220, 255),
                    random.randint(220, 255)
                )
                draw.point((x, y), fill=color)

        # Добавляем линии для усложнения распознавания
        for i in range(6):
            line_color = (
                random.randint(160, 200),
                random.randint(160, 200),
                random.randint(160, 200)
            )
            draw.line(
                [
                    (random.randint(0, width), random.randint(0, height)),
                    (random.randint(0, width), random.randint(0, height))
                ],
                fill=line_color,
                width=2
            )

        # Пытаемся использовать встроенный шрифт
        try:
            # Увеличиваем размер шрифта
            font = ImageFont.load_default().font_variant(size=48)
        except Exception:
            try:
                # Создаем базовый шрифт, если load_default не сработает
                font = ImageFont.truetype("arial.ttf", 48)
            except Exception:
                # Если не удалось загрузить шрифт, используем базовый шрифт
                font = None

        # Рассчитываем положение текста (примерно по центру)
        text_width = width // 2
        text_height = height // 2
        position = (width // 8, height // 4)

        # Промежуток между символами
        letter_spacing = width // (len(text) + 2)

        # Рисуем каждую букву с небольшим смещением
        for i, char in enumerate(text):
            # Случайный темный цвет для каждого символа
            char_color = (
                random.randint(0, 50),
                random.randint(0, 50),
                random.randint(0, 50)
            )

            # Рисуем символ со смещением
            x_pos = position[0] + i * letter_spacing
            y_pos = position[1] + random.randint(-10, 10)

            # Рисуем с небольшим наклоном
            if font:
                draw.text((x_pos, y_pos), char, font=font, fill=char_color)
            else:
                # Если шрифт не загрузился, используем базовый метод
                draw.text((x_pos, y_pos), char, fill=char_color)

        # Конвертируем изображение в base64 для отображения в HTML
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    @staticmethod
    def generate_captcha():
        """Генерация CAPTCHA (текст и изображение)"""
        captcha_text = Captcha.generate_captcha_text()
        captcha_image = Captcha.generate_captcha_image(captcha_text)
        captcha_id = get_random_string(32)

        return {
            'captcha_id': captcha_id,
            'captcha_image': captcha_image,
            'captcha_text': f"{captcha_text}$_"
        }

    @staticmethod
    def verify_captcha(input_text, stored_text):
        """Проверка введенного текста CAPTCHA"""
        if not input_text or not stored_text:
            logger.warning(f"Empty CAPTCHA input or stored text: input='{input_text}', stored='{stored_text}'")
            return False

        input_cleaned = input_text.strip().upper()
        stored_cleaned = stored_text.strip().upper()

        # Логируем для отладки
        logger.info(f"CAPTCHA verification: input='{input_cleaned}', stored='{stored_cleaned}'")

        # Проверяем равенство
        is_valid = input_cleaned == stored_cleaned
        logger.info(f"CAPTCHA validation result: {is_valid}")

        return is_valid
