"""
passenger_wsgi.py — cPanel Phusion Passenger entry point
This file MUST be called passenger_wsgi.py for cPanel to recognise it.
NOTE: cPanel may overwrite this file on restart — use the Restart button (not Stop/Start).
"""
import sys, os

# Add project root to path
INTERP = os.path.join(os.environ.get("HOME",""), "virtualenv", "vcdp-cis", "bin", "python3")
if sys.executable != INTERP and os.path.exists(INTERP):
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

# Import the Flask application — cPanel needs it named 'application'
from app import application
