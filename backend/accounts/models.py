from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager
)
from datetime import date

# -------------------
# User Manager
# -------------------
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        extra_fields.setdefault("login_id", email)
        extra_fields.setdefault("is_active", True)
        user = self.model(
            email=email,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")
        extra_fields.setdefault("must_change_password", False)
        return self.create_user(email, password, **extra_fields)


# -------------------
# Custom User Model
# -------------------
class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ("ADMIN", "Admin"),
        ("HR", "HR"),
        ("EMP", "Employee"),
        ("INT", "Intern"),
    )

    login_id = models.CharField(max_length=255, unique=True)
    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)

    #: The tenant boundary. Every tenant-scoped query filters on this FK.
    #: It replaces the free-text `company_name` that let anyone join an existing
    #: customer's tenant by typing its name at signup (audit V-01).
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="members",
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="EMP")
    date_of_joining = models.DateField(default=date.today)
    department = models.CharField(max_length=100, blank=True, default="")
    employment_type = models.CharField(max_length=50, blank=True, default="")

    must_change_password = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "login_id"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        indexes = [
            models.Index(fields=["organization", "role"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return self.login_id

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.login_id
