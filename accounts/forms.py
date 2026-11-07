from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    """Create a user using Django's built-in password validation and hashing."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
