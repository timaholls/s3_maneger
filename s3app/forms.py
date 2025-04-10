from django import forms
from django.contrib.auth.models import User
from .models import UserPermission


class LoginForm(forms.Form):
    """Форма для авторизации пользователя"""
    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите имя пользователя',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль',
            'autocomplete': 'current-password'
        })
    )
    captcha_input = forms.CharField(
        label="Введите текст с картинки",
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите CAPTCHA'
        })
    )


class CreateFolderForm(forms.Form):
    """Форма для создания новой папки"""
    folder_name = forms.CharField(
        label="Название папки",
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите название папки'
        })
    )


class UploadFileForm(forms.Form):
    """Форма для загрузки файла"""
    file = forms.FileField(
        label="Выберите файл",
        widget=forms.FileInput(attrs={
            'class': 'form-control'
        })
    )


class UserPermissionForm(forms.ModelForm):
    """Форма для назначения прав пользователя"""

    # Explicitly define folder_path to override required status
    folder_path = forms.CharField(
        label="Путь к папке в S3",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'folder/subfolder/ (пусто = корень)'
        }),
        help_text="Путь к папке без начального '/'. Оставьте пустым для корневой папки.",
        max_length=1024
    )

    class Meta:
        model = UserPermission
        fields = ['user', 'folder_path', 'can_read', 'can_write', 'can_delete', 'can_move']
        widgets = {
            'user': forms.HiddenInput(),
            'can_read': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'can_write': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'can_delete': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'can_move': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class UserCreationForm(forms.ModelForm):
    """Форма для создания пользователя"""
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль',
            'autocomplete': 'new-password'
        }),
        required=False,
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Подтвердите пароль',
            'autocomplete': 'new-password'
        }),
        required=False,
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Имя пользователя',
                'autocomplete': 'username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email адрес',
                'autocomplete': 'email'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Имя',
                'autocomplete': 'given-name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Фамилия',
                'autocomplete': 'family-name'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def clean_password2(self):
        # Валидация совпадения паролей
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        # Если это создание нового пользователя (нет instance.pk), то пароль обязателен
        if not self.instance.pk and not password1:
            raise forms.ValidationError("Пароль обязателен при создании нового пользователя")

        # Проверка совпадения паролей, только если хотя бы один из них указан
        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("Пароли не совпадают")

        return password2

    def save(self, commit=True):
        # Сохранение пароля в хешированном виде
        user = super().save(commit=False)

        # Устанавливаем пароль только если он был указан
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        elif not self.instance.pk:
            user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()
        return user


from django.contrib.auth.forms import PasswordChangeForm as AuthPasswordChangeForm

class CustomPasswordChangeForm(AuthPasswordChangeForm):
    """Кастомная форма смены пароля с Bootstrap классами"""
    old_password = forms.CharField(
        label="Старый пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
            'placeholder': 'Введите текущий пароль'
        })
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'placeholder': 'Введите новый пароль'
        })
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'placeholder': 'Подтвердите новый пароль'
        })
    )
