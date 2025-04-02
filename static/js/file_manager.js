/**
 * Скрипт управления множественным выбором файлов
 */
document.addEventListener('DOMContentLoaded', function() {
    const multiActionPanel = document.getElementById('multiActionPanel');
    const selectedCountEl = document.getElementById('selectedCount');
    const downloadSelectedBtn = document.getElementById('downloadSelected');
    const deleteSelectedBtn = document.getElementById('deleteSelected');
    const selectAllBtn = document.getElementById('selectAll');
    const deselectAllBtn = document.getElementById('deselectAll');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const itemCheckboxes = document.querySelectorAll('.item-checkbox');

    let selectedItems = new Set();

    // Обновление состояния панели множественных действий
    function updateMultiActionPanel() {
        const selectedCount = selectedItems.size;
        selectedCountEl.textContent = selectedCount;

        if (selectedCount > 0) {
            multiActionPanel.classList.add('active');
            downloadSelectedBtn.disabled = false;
            deleteSelectedBtn.disabled = false;
        } else {
            multiActionPanel.classList.remove('active');
            downloadSelectedBtn.disabled = true;
            deleteSelectedBtn.disabled = true;
        }

        // Обновить состояние главного чекбокса
        if (itemCheckboxes.length > 0) {
            if (selectedCount === itemCheckboxes.length) {
                selectAllCheckbox.checked = true;
                selectAllCheckbox.indeterminate = false;
            } else if (selectedCount > 0) {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = true;
            } else {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = false;
            }
        }
    }

    // Обработка клика по чекбоксу отдельного элемента
    function handleItemCheckboxClick(event) {
        const checkbox = event.target;
        const itemType = checkbox.dataset.type;
        const itemPath = checkbox.dataset.path;
        const itemKey = `${itemType}:${itemPath}`;

        if (checkbox.checked) {
            selectedItems.add(itemKey);
        } else {
            selectedItems.delete(itemKey);
        }

        updateMultiActionPanel();
    }

    // Обработка клика по главному чекбоксу
    function handleSelectAllCheckboxClick(event) {
        const checked = event.target.checked;

        itemCheckboxes.forEach(checkbox => {
            checkbox.checked = checked;

            const itemType = checkbox.dataset.type;
            const itemPath = checkbox.dataset.path;
            const itemKey = `${itemType}:${itemPath}`;

            if (checked) {
                selectedItems.add(itemKey);
            } else {
                selectedItems.delete(itemKey);
            }
        });

        updateMultiActionPanel();
    }

    // Кнопка "Выбрать все"
    selectAllBtn.addEventListener('click', function() {
        itemCheckboxes.forEach(checkbox => {
            checkbox.checked = true;

            const itemType = checkbox.dataset.type;
            const itemPath = checkbox.dataset.path;
            const itemKey = `${itemType}:${itemPath}`;

            selectedItems.add(itemKey);
        });

        updateMultiActionPanel();
    });

    // Кнопка "Отменить выбор"
    deselectAllBtn.addEventListener('click', function() {
        itemCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });

        selectedItems.clear();
        updateMultiActionPanel();
    });

    // Кнопка "Скачать выбранное"
    downloadSelectedBtn.addEventListener('click', function() {
        const fileItems = Array.from(selectedItems)
            .filter(item => item.startsWith('file:'))
            .map(item => item.split(':')[1]);

        if (fileItems.length > 0) {
            // Для одиночного файла - прямое скачивание
            if (fileItems.length === 1) {
                window.location.href = `/s3app/download-file/${fileItems[0]}`;
                return;
            }

            // Для множественного выбора - запрос на создание архива
            const formData = new FormData();
            fileItems.forEach(path => {
                formData.append('files[]', path);
            });

            // Здесь должен быть запрос к серверу для создания ZIP-архива
            fetch('/download-multiple/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCsrfToken()
                }
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Ошибка при создании архива');
            })
            .then(blob => {
                // Создание ссылки для скачивания архива
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'files.zip';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            })
            .catch(error => {
                alert(error.message);
            });
        } else {
            alert('Выберите хотя бы один файл для скачивания');
        }
    });

    // Кнопка "Удалить выбранное"
    deleteSelectedBtn.addEventListener('click', function() {
        if (selectedItems.size === 0) {
            alert('Выберите хотя бы один элемент для удаления');
            return;
        }

        const fileCount = Array.from(selectedItems).filter(item => item.startsWith('file:')).length;
        const folderCount = Array.from(selectedItems).filter(item => item.startsWith('folder:')).length;

        let confirmMessage = 'Вы уверены, что хотите удалить ';
        if (fileCount > 0 && folderCount > 0) {
            confirmMessage += `${fileCount} файл(ов) и ${folderCount} папку(папок)?`;
        } else if (fileCount > 0) {
            confirmMessage += `${fileCount} файл(ов)?`;
        } else {
            confirmMessage += `${folderCount} папку(папок) и всё их содержимое?`;
        }

        if (confirm(confirmMessage)) {
            const formData = new FormData();
            selectedItems.forEach(item => {
                const [type, path] = item.split(':');
                formData.append(`${type}s[]`, path);
            });

            // Здесь должен быть запрос к серверу для удаления выбранных элементов
            fetch('/delete-multiple/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCsrfToken()
                }
            })
            .then(response => {
                if (response.ok) {
                    // Перезагрузка страницы после успешного удаления
                    window.location.reload();
                } else {
                    throw new Error('Ошибка при удалении элементов');
                }
            })
            .catch(error => {
                alert(error.message);
            });
        }
    });

    // Получение CSRF-токена из куки
    function getCsrfToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    }

    // Привязка обработчиков событий
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', handleSelectAllCheckboxClick);
    }

    itemCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', handleItemCheckboxClick);
    });

    // Инициализация состояния панели
    updateMultiActionPanel();
});
