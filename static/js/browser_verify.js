// static/js/browser_verify.js

// Функция для получения значения cookie по имени (нужна для CSRF)
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Функция для выполнения проверки
async function runBrowserCheck() {
    const validationUrl = '/browser-challenge/validate/'; // URL валидации из settings.py
    const csrfToken = getCookie('csrftoken'); // Получаем CSRF токен

    const loader = document.getElementById('loader');
    const errorMessage = document.getElementById('error-message');
    const retryBtn = document.getElementById('retry-btn');

    loader.style.display = 'block';
    errorMessage.style.display = 'none';
    retryBtn.style.display = 'none';

    try {
        const response = await fetch(validationUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json', // Можно и пустое тело отправить, если серверу не нужны данные
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest', // Полезно для Django, чтобы отличить AJAX
            },
            body: JSON.stringify({ verification_signal: 'running_js' }) // Отправляем простой сигнал
        });

        if (response.ok) {
            // Успех! Сервер установил cookie. Перенаправляем пользователя.
            const urlParams = new URLSearchParams(window.location.search);
            const nextUrl = urlParams.get('next') || '/'; // Получаем исходный URL или идем в корень
            console.log('Browser verified. Redirecting to:', nextUrl);
            window.location.href = nextUrl; // Перенаправляем
        } else {
            // Сервер вернул ошибку
            console.error('Browser verification failed on server:', response.status, response.statusText);
            errorMessage.textContent = `Ошибка проверки на сервере (Код: ${response.status}). Попробуйте снова.`;
            errorMessage.style.display = 'block';
            loader.style.display = 'none';
            retryBtn.style.display = 'block';
        }
    } catch (error) {
        // Ошибка сети или JS
        console.error('Browser verification request failed:', error);
        errorMessage.textContent = 'Не удалось выполнить проверку. Проверьте ваше интернет-соединение и попробуйте снова.';
        errorMessage.style.display = 'block';
        loader.style.display = 'none';
        retryBtn.style.display = 'block';
    }
}

// Запускаем проверку при загрузке страницы
window.addEventListener('load', runBrowserCheck);