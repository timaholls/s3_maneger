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
        required=False,  # <<< THIS IS THE FIX
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'folder/subfolder/ (пусто = корень)' # Shortened placeholder
        }),
        help_text="Путь к папке без начального '/'. Оставьте пустым для корневой папки.",
        max_length=1024 # Match model max_length if needed
    )

    class Meta:
        model = UserPermission
        fields = ['user', 'folder_path', 'can_read', 'can_write', 'can_delete']
        widgets = {
            # Keep user widget definition if needed, although it might be hidden/set in view
            'user': forms.HiddenInput(), # Assuming user is set in the view, hide it. Use Select if user chooses.
            # folder_path widget is now defined above
            'can_read': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'can_write': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'can_delete': forms.CheckboxInput(attrs={
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
        })
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Подтвердите пароль',
            'autocomplete': 'new-password'
        })
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
