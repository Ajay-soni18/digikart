"""
Custom user model for Digikart.

Accounts are created EXCLUSIVELY through Google Sign-In: the frontend obtains a
Google ID token, the backend verifies it (apps/accounts/google.py) and then
creates or logs in the matching user. There is no email/password signup. Email
is the login identifier (no separate username) and is treated as verified
because Google verified it. Staff/superusers are still created locally with a
password (createsuperuser) for Django's own admin; flip `is_staff=True` on a
Google-created user to give it access to the React admin dashboard.

`first_name` / `last_name` come from the Google profile (given/family name) and,
together with the email, are what the per-note watermark displays.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager that creates users keyed by email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, full_name, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email).lower()
        user = self.model(
            email=email,
            full_name=full_name.strip() if full_name else "",
            **extra_fields,
        )
        if password:
            user.set_password(password)  # hashes the password (staff/superuser)
        else:
            # Google-only accounts never sign in with a password.
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, full_name="", password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, full_name, password, **extra_fields)

    def create_superuser(self, email, full_name="", password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, full_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """A registered student or staff member. Email is the unique login id."""

    email = models.EmailField("email address", unique=True)
    full_name = models.CharField("full name", max_length=150, blank=True)

    # Google profile names. `first_name` + `last_name` + `email` are what the
    # per-note watermark shows (drawn client-side on each page). Either name may
    # be blank if Google didn't provide it — the watermark degrades gracefully.
    first_name = models.CharField("first name", max_length=150, blank=True, default="")
    last_name = models.CharField("last name", max_length=150, blank=True, default="")

    # Google's stable, unique account identifier (the ID token's `sub` claim).
    # One Google account ⇄ one user, so it's UNIQUE. NULL for local staff/super-
    # users created with createsuperuser (no Google link); multiple NULLs are
    # allowed by the DB and skipped by uniqueness checks.
    google_sub = models.CharField(
        "Google subject id", max_length=255, unique=True, null=True, blank=True
    )
    # Google profile picture URL (optional; handy for the dashboard avatar).
    picture = models.URLField("profile picture", max_length=500, blank=True, default="")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False, help_text="Can access the admin/staff tooling."
    )
    date_joined = models.DateTimeField(default=timezone.now)

    # Single-device login: the id of the one currently-active session. Every
    # issued token carries this value ("sid"); a token whose sid != this is
    # rejected. Rotating it (on each new login) instantly logs out other devices.
    current_session_key = models.CharField(max_length=40, blank=True, default="")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]  # prompted by createsuperuser

    class Meta:
        ordering = ["-date_joined"]
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return f"{self.full_name} <{self.email}>" if self.full_name else self.email

    def start_new_session(self):
        """Begin a fresh single-device session, invalidating any existing one.
        Returns the new session id to embed in the issued tokens."""
        self.current_session_key = uuid.uuid4().hex
        self.save(update_fields=["current_session_key"])
        return self.current_session_key

    def end_session(self):
        """Clear the active session so every outstanding token is rejected."""
        self.current_session_key = ""
        self.save(update_fields=["current_session_key"])

    def get_full_name(self):
        return self.full_name or f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        if self.first_name:
            return self.first_name
        return self.full_name.split(" ")[0] if self.full_name else self.email


class Profile(models.Model):
    """Optional extra buyer details. Kept separate so the core User stays lean
    and we can grow buyer-facing fields without touching auth.

    Deliberately domain-neutral: this used to carry MBBS year choices, which
    only made sense while the catalog was a medical curriculum. `headline` is
    free text so it fits a student, a photographer or anyone else.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organisation = models.CharField(
        max_length=200, blank=True, help_text="College, studio, company — whatever fits.",
    )
    headline = models.CharField(
        max_length=200, blank=True, help_text='Free text, e.g. "2nd year medical student".',
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user}"
