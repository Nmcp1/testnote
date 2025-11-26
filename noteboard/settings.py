from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-_l-d1a94owm)@#^2)-_-k6h**db2o4=5n4h7np$l3q=*&55j$z'

# ⚠️ Render necesita DEBUG = False para que admin funcione bien con CSRF
DEBUG = False

# Permitir todos los hosts (Render usa dominio dinámico)
ALLOWED_HOSTS = ["*"]


# ---------------------------------------------------------
# APLICACIONES
# ---------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'notes',  # nuestra app
]


# ---------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ⭐ NECESARIO PARA RENDER — Django debe reconocer HTTPS detrás del proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ⭐ NECESARIO PARA ADMIN / LOGIN EN RENDER
CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
]


# ---------------------------------------------------------
# TEMPLATES
# ---------------------------------------------------------

ROOT_URLCONF = 'noteboard.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'notes.context_processors.notifications_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'noteboard.wsgi.application'


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

DATABASES = {
    'default': dj_database_url.config(
        # Fallback a SQLite si no hay DATABASE_URL (por ejemplo en tu PC)
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=True,
    )
}


# ---------------------------------------------------------
# AUTH PASSWORD VALIDATORS (DESACTIVADOS)
# ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = []


# ---------------------------------------------------------
# LOCALIZACIÓN
# ---------------------------------------------------------

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'

USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------
# ARCHIVOS ESTÁTICOS (IMPORTANTE PARA RENDER)
# ---------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'   # Render usará esta carpeta al hacer collectstatic
STATICFILES_DIRS = [BASE_DIR / 'static']


# ---------------------------------------------------------
# DEFAULTS
# ---------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# LOGIN REDIRECTS
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'
