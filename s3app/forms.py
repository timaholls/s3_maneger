from django import forms
from django.contrib.auth.models import User
from .models import UserPermission


class LoginForm(forms.Form):
    """Форма для авторизации пользователя"""
    username = forms.CharField(
        label="Имя пользователя",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Имя пользователя'})
    )
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Пароль'})
    )
    # --- ДОБАВЛЕНО ПОЛЕ CAPTCHA ---
    captcha_input = forms.CharField(
        label="Введите текст с картинки",
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CAPTCHA'})
    )

class CreateFolderForm(forms.Form):
    """Форма для создания новой папки"""
    folder_name = forms.CharField(
        label="Название папки",
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название папки'})
    )


class UploadFileForm(forms.Form):
    """Форма для загрузки файла"""
    file = forms.FileField(
        label="Выберите файл",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )


class UserPermissionForm(forms.ModelForm):
    """Форма для назначения прав пользователя"""
    class Meta:
        model = UserPermission
        fields = ['user', 'folder_path', 'can_read', 'can_write', 'can_delete']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'folder_path': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Путь к папке'}),
            'can_read': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'can_write': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'can_delete': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class UserCreationForm(forms.ModelForm):
    """Форма для создания пользователя"""
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Пароль'})
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Подтверждение пароля'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Имя пользователя'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Имя'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Фамилия'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_password2(self):
        # Валидация совпадения паролей
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают")
        return password2

    def save(self, commit=True):
        # Сохранение пароля в хешированном виде
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

from django.contrib.auth.forms import PasswordChangeForm as AuthPasswordChangeForm

class CustomPasswordChangeForm(AuthPasswordChangeForm):
    """Кастомная форма смены пароля с Bootstrap классами"""
    old_password = forms.CharField(
        label="Старый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'})
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'})
    )
    new_password2 = forms.CharField(
        label="Подтверждение нового пароля",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'})
    )