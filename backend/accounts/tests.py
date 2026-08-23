from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from organizations.models import Organization

from .models import CustomUser


class CompanySignupTest(APITestCase):
    """Signup creates a new organization and its owner.

    The previous test here asserted that registration produced an HR account with
    is_staff=True and is_approved=False, which matched neither the code nor the
    intent -- the view actually promoted every signup to ADMIN of whatever company
    name was submitted (audit V-01).
    """

    def _payload(self, **overrides):
        return {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password": "s3cure-Passw0rd!",
            "company_name": "Test Company",
            **overrides,
        }

    def test_signup_creates_organization_and_owner(self):
        response = self.client.post(
            reverse("company-signup"), self._payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        organization = Organization.objects.get()
        self.assertEqual(organization.name, "Test Company")
        self.assertEqual(organization.slug, "test-company")

        user = CustomUser.objects.get()
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.role, "ADMIN")
        self.assertEqual(user.organization_id, organization.id)
        self.assertEqual(organization.owner_id, user.id)
        self.assertTrue(user.is_approved)
        self.assertFalse(user.must_change_password)
        # Owning a tenant is not the same as being a Django superuser.
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_signup_rejects_a_taken_company_name(self):
        self.client.post(reverse("company-signup"), self._payload(), format="json")
        response = self.client.post(
            reverse("company-signup"),
            self._payload(email="second@example.com"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Organization.objects.count(), 1)

    def test_signup_rejects_a_duplicate_email(self):
        self.client.post(reverse("company-signup"), self._payload(), format="json")
        response = self.client.post(
            reverse("company-signup"),
            self._payload(company_name="Another Company"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_signup_rejects_a_weak_password(self):
        response = self.client.post(
            reverse("company-signup"), self._payload(password="password"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_signup_rejects_an_unknown_timezone(self):
        response = self.client.post(
            reverse("company-signup"), self._payload(timezone="Mars/Olympus"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)

    def test_signup_stores_the_organization_timezone(self):
        response = self.client.post(
            reverse("company-signup"), self._payload(timezone="Asia/Kolkata"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Organization.objects.get().timezone, "Asia/Kolkata")
