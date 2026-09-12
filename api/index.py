import sys
import os
from pathlib import Path

# Add project root and tripplanner subfolder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
TRIPPLANNER_DIR = BASE_DIR / "tripplanner"

if str(TRIPPLANNER_DIR) not in sys.path:
    sys.path.insert(0, str(TRIPPLANNER_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tripplanner.settings')

from tripplanner.wsgi import app

# Export for Vercel serverless function
handler = app
