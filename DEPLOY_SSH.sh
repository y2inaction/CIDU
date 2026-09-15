#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# VCDP CIDU — One-Command cPanel SSH Deployment Script
# Run this ONCE after uploading vcdp-cis-system.zip to your server.
# Usage: bash DEPLOY_SSH.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e
BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${BLUE}[VCDP]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  VCDP CIDU — cPanel SSH Deployment"
echo "  Green Allied Trust Nig. Ltd"
echo "  Powered by Noblen Technologies Limited"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Detect project root ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
log "Project root: $SCRIPT_DIR"

# ── Find virtualenv ───────────────────────────────────────────────────────
log "Looking for virtual environment..."
VENV=""
for path in \
    "$HOME/virtualenv/vcdp-cis/3.11/bin/activate" \
    "$HOME/virtualenv/vcdp-cis/bin/activate" \
    "$HOME/virtualenv/vcdp-cis/3.10/bin/activate" \
    "$HOME/virtualenv/vcdp-cis/3.9/bin/activate" \
    "$SCRIPT_DIR/venv/bin/activate"; do
    if [ -f "$path" ]; then
        VENV="$path"
        ok "Found virtualenv: $path"
        break
    fi
done

if [ -z "$VENV" ]; then
    warn "No virtualenv found — creating one..."
    python3 -m venv "$HOME/virtualenv/vcdp-cis"
    VENV="$HOME/virtualenv/vcdp-cis/bin/activate"
fi
source "$VENV"

# ── Add PyMySQL for MySQL support ─────────────────────────────────────────
log "Ensuring PyMySQL is in requirements.txt..."
grep -q "PyMySQL" requirements.txt || echo "PyMySQL==1.1.0" >> requirements.txt
ok "PyMySQL entry confirmed"

# ── Install dependencies ──────────────────────────────────────────────────
log "Installing Python dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "Dependencies installed"

# ── Check .env exists ─────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env file not found — creating from template..."
    cat > .env << 'ENVEOF'
SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_STRING
DATABASE_URL=mysql+pymysql://DB_USER:DB_PASSWORD@localhost/DB_NAME
FLASK_ENV=production
NO_SCHEDULER=1
TERMII_API_KEY=TLNTscjMCFrXMfiPFvOUwbaIrwXkMsDaeTCajhJsBhCGYEPBehPWTnJYIOywmW
SENDER_ID=VCDP
SMS_COST_KOBO=600
TUYA_DATA_CENTER=eu
ENVEOF
    err ".env created but DATABASE_URL is not set. Edit .env with your MySQL credentials then re-run this script."
fi

# ── Validate DATABASE_URL is configured ───────────────────────────────────
source <(grep -v '^#' .env | grep -v '^$')
if [[ "$DATABASE_URL" == *"DB_USER"* ]] || [[ "$DATABASE_URL" == *"DB_PASSWORD"* ]]; then
    err "DATABASE_URL in .env still has placeholder values. Edit .env with your actual MySQL credentials."
fi
ok ".env loaded"

# ── Run database migrations ───────────────────────────────────────────────
log "Running database migrations..."
export FLASK_APP=app.py
export $(grep -v '^#' .env | grep -v '^$' | xargs)

if [ -d "migrations" ]; then
    flask db upgrade 2>&1 | tail -5
else
    log "No migrations folder found — initializing..."
    flask db init
    flask db migrate -m "initial"
    flask db upgrade
fi
ok "Database ready"

# ── Create log directory ──────────────────────────────────────────────────
mkdir -p "$HOME/logs"
ok "Logs directory: $HOME/logs"

# ── Test app starts ───────────────────────────────────────────────────────
log "Testing application import..."
python3 -c "
import os
os.environ.setdefault('FLASK_ENV','production')
from app import create_app
app = create_app()
with app.app_context():
    from models import User, ProgrammeLGA, Template
    print('  Users:', User.query.count())
    print('  LGAs:', ProgrammeLGA.query.count())
    print('  SMS Templates:', Template.query.count())
"
ok "Application test passed"

# ── Print cron job instructions ───────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅  DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. Restart your Python App in cPanel → Setup Python App"
echo "  2. Visit your domain and verify the login page loads"
echo "  3. Add the following Cron Job in cPanel (Mon/Thu 7AM WAT):"
echo ""
echo "     0 6 * * 1,4 source $VENV && cd $SCRIPT_DIR && export \$(cat .env | grep -v '^#' | xargs) && flask trigger-broadcast >> $HOME/logs/vcdp-cron.log 2>&1"
echo ""
echo "  4. Login: yusufyau / VCDP@Owner2026!"
echo ""
