"""
Django settings for the Hostel Management System.

Configuration comes from environment variables so the same code runs on a
developer laptop, in CI and in the demo. The database is PostgreSQL (SAD 3.6).
"""

import os
import sys
from pathlib import Path

from django.contrib.messages import constants as messages

# Email defaults to the console in development; configure SMTP through environment variables
# in deployment. Secrets belong in the untracked .env file, never in source control.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").strip().lower() in ("1", "true", "yes", "on")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "hostel-management@localhost")

# Shared credential for authenticated RFID/biometric gate devices.
# Never commit the actual secret.
GATE_DEVICE_API_KEY = os.environ.get("GATE_DEVICE_API_KEY", "")

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes"}


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me-in-production"
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


INSTALLED_APPS = [
    "hms.apps.HMSAdminConfig",  # Django admin with the HMS site (hms/admin_site.py)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "django_otp",
    "django_otp.plugins.otp_totp",
    # One Django app per service module (SAD 3.4, 3.5)
    "apps.accounts",
    "apps.admissions",
    "apps.fees",
    "apps.gate",
    "apps.mess",
    "apps.complaints",
    "apps.visitors",
    "apps.reporting",
    "apps.audit",
]

MIDDLEWARE = [
    "hms.api.TraceIdMiddleware",
    "hms.security.InputGuardMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.audit.context.AuditContextMiddleware",
    "apps.accounts.middleware.MFARequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hms.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "hms.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "hms.navigation.navigation",
            ],
            "builtins": ["hms.templatetags.hms_extras"],
        },
    },
]

WSGI_APPLICATION = "hms.wsgi.application"


# PostgreSQL everywhere (SAD 3.6). The defaults match the local setup in README.md.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "hms"),
        "USER": os.environ.get("POSTGRES_USER", "hms"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "hms"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}


# The academic session new applications belong to, and the student-records adapter (SRS 3.3).
ACADEMIC_SESSION = os.environ.get("HMS_ACADEMIC_SESSION", "2026-27")
HMS_ERP_ADAPTER = os.environ.get("HMS_ERP_ADAPTER", "apps.admissions.erp.StubERP")

# Fees: invoices fall due this many days after they are issued (HMS-F-013).
FEE_DUE_DAYS = int(os.environ.get("HMS_FEE_DUE_DAYS", "15"))

# The payment gateway. The shared secret signs the callback it sends us (HMS-SR-005); the
# bundled gateway is a stand-in for a real PCI-DSS provider (see DEVIATIONS.md).
PAYMENT_GATEWAY_SECRET = os.environ.get("HMS_PAYMENT_SECRET", "dev-only-gateway-secret")
PAYMENT_GATEWAY_ENABLED = env_bool("HMS_PAYMENT_GATEWAY_ENABLED", True)

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Passwords are stored only as salted Argon2 hashes (HMS-SR-003). PBKDF2 stays in the
# list so an older hash still verifies and is upgraded to Argon2 on the next sign-in.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
if "test" in sys.argv:
    # Argon2 is deliberately slow; tests that check hashing override this setting.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# A session ends after 15 minutes without a request, and logout deletes it on the
# server so a copied session cookie stops working (HMS-SR-002).
SESSION_COOKIE_AGE = 15 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Warden and Administrator sign-ins need a TOTP code from an authenticator app (HMS-SR-003).
OTP_TOTP_ISSUER = "Hostel Management System"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "hms.api.exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# HTTPS (HMS-SR-001). Outside development every request must arrive over TLS: plain HTTP is
# redirected, browsers are told to stay on HTTPS, and cookies are never sent over HTTP. The
# TLS handshake itself, with TLS 1.2 as the minimum, is configured on the web server in front
# of Django (deploy/nginx.conf.example). Set HMS_BEHIND_PROXY when that server terminates TLS.
FORCE_HTTPS = env_bool("HMS_FORCE_HTTPS", not DEBUG) and "test" not in sys.argv
SECURE_SSL_REDIRECT = FORCE_HTTPS
SECURE_HSTS_SECONDS = 31536000 if FORCE_HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = FORCE_HTTPS
SESSION_COOKIE_SECURE = FORCE_HTTPS
CSRF_COOKIE_SECURE = FORCE_HTTPS
if env_bool("HMS_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Not asking browsers to preload the domain: that is a one-way commitment for the institution.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Map Django message levels onto Bootstrap alert classes.
MESSAGE_TAGS = {messages.ERROR: "danger"}
