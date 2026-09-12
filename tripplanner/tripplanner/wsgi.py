"""
WSGI config for tripplanner project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tripplanner.settings')

application = get_wsgi_application()
app = application

# Run auto-migration on Vercel cold start for SQLite in /tmp
if os.getenv("VERCEL") == "1" or os.getenv("VERCEL_ENV") is not None:
    try:
        from django.core.management import call_command
        call_command("migrate", verbosity=0, interactive=False)
    except Exception as e:
        print("Vercel auto-migration status:", e)


