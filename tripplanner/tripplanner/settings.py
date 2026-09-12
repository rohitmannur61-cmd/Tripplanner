"""
Django settings for tripplanner project.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file(BASE_DIR / ".env")

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-p&78+1b1e9-1-2vi^n+eb1rhxk$unuf1469#tbmecr85n2$$(x')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".ngrok-free.dev",
    ".vercel.app",
    "*",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.ngrok-free.dev",
    "https://*.vercel.app",
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'planner',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tripplanner.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'tripplanner.wsgi.application'

# Database configuration
is_vercel = os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None
selected_db = os.getenv("DJANGO_DB", "").strip().lower()
cloud_db_url = (
    os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRES_URL_NON_POOLING")
    or os.getenv("STORAGE_URL")
    or os.getenv("DATABASE_URL")
)


def get_sqlite_db_path() -> Path:
    if is_vercel:
        target_path = Path("/tmp/db.sqlite3")
        if not target_path.exists():
            copied = False
            for source_candidate in (BASE_DIR / "db.sqlite3", BASE_DIR.parent / "db.sqlite3"):
                if source_candidate.exists():
                    try:
                        import shutil
                        shutil.copyfile(source_candidate, target_path)
                        copied = True
                        break
                    except Exception:
                        pass
            if not copied:
                try:
                    target_path.touch(exist_ok=True)
                except Exception:
                    pass
        return target_path
    return BASE_DIR / "db.sqlite3"



if cloud_db_url:
    try:
        import dj_database_url
        DATABASES = {
            "default": dj_database_url.parse(cloud_db_url, conn_max_age=60)
        }
    except Exception:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": get_sqlite_db_path(),
            }
        }
elif is_vercel:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": get_sqlite_db_path(),
        }
    }
elif selected_db == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": get_sqlite_db_path(),
        }
    }
elif (selected_db == "mysql") or os.getenv("MYSQL_DATABASE"):
    mysql_engine = os.getenv("MYSQL_ENGINE", "").strip().lower()
    engine = "django.db.backends.mysql"
    if mysql_engine in {"connector", "mysql-connector", "mysqlconnector"}:
        engine = "mysql.connector.django"

    db_name = os.getenv("MYSQL_DATABASE", "tripplanner")

    DATABASES = {
        "default": {
            "ENGINE": engine,
            "NAME": db_name,
            "USER": os.getenv("MYSQL_USER", "root"),
            "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
            "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.getenv("MYSQL_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": get_sqlite_db_path(),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

SESSION_EXPIRE_AT_BROWSER_CLOSE = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "noreply@tripplanner.local")

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Google Places API (New) Configuration
GOOGLE_PLACES_API_KEY = os.getenv(
    "GOOGLE_PLACES_API_KEY",
    os.getenv("GOOGLE_SEARCH_PLACES_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
)

