from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class AccountFlowTests(TestCase):
    def test_signup_creates_user_with_hashed_password(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "maya",
                "email": "maya@example.com",
                "password1": "N4v!gation-Leaf-27",
                "password2": "N4v!gation-Leaf-27",
            },
        )

        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(username="maya")
        self.assertTrue(user.check_password("N4v!gation-Leaf-27"))
        self.assertNotEqual(user.password, "N4v!gation-Leaf-27")

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "maya",
                "email": "maya@example.com",
                "password1": "N4v!gation-Leaf-27",
                "password2": "Different-Password-28",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="maya").exists())

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}",
        )

    def test_login_and_post_logout(self):
        User.objects.create_user(username="maya", password="N4v!gation-Leaf-27")

        login_response = self.client.post(
            reverse("accounts:login"),
            {"username": "maya", "password": "N4v!gation-Leaf-27"},
        )
        self.assertRedirects(login_response, reverse("accounts:dashboard"))
        self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 200)

        logout_response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(logout_response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_only_accepts_post(self):
        User.objects.create_user(username="maya", password="N4v!gation-Leaf-27")
        self.client.login(username="maya", password="N4v!gation-Leaf-27")

        response = self.client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 405)

    def test_logout_requires_csrf_token(self):
        user = User.objects.create_user(username="maya", password="N4v!gation-Leaf-27")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        response = csrf_client.post(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 403)

    def test_signup_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse("accounts:signup"),
            {
                "username": "maya",
                "email": "maya@example.com",
                "password1": "N4v!gation-Leaf-27",
                "password2": "N4v!gation-Leaf-27",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="maya").exists())
