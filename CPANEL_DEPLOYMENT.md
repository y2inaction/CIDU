# VCDP CIDU — cPanel Deployment Guide
# Green Allied Trust Nig. Ltd | Powered by Noblen Technologies Limited

---

## BEFORE YOU START — What you need ready

- [ ] Your cPanel login credentials
- [ ] SSH access (username, server IP, password)
- [ ] Your domain/subdomain decided (e.g. `cis.greenalliedtrust.com`)
- [ ] The `vcdp-cis-system.zip` file downloaded

---

## STEP 1 — Create a Subdomain (if needed)

If hosting on a subdomain like `cis.yourdomain.com`:

1. cPanel → **Domains** → **Create A New Domain**
2. Enter: `cis.yourdomain.com`
3. Document root: `/home/USERNAME/cis.yourdomain.com`
4. Click **Submit**

---

## STEP 2 — Check for Python App Support

cPanel → **Software** section → look for **"Setup Python App"**

- ✅ **Found it** → Continue with Step 3 below
- ❌ **Not found** → Use the SSH-only method in **Appendix A** at the bottom

---

## STEP 3 — Create the Python Application

1. Click **Setup Python App** → **Create Application**
2. Fill in:

| Field | Value |
|-------|-------|
| Python version | **3.11** (or closest available — do NOT use 3.6/3.7/3.8) |
| Application root | `vcdp-cis` |
| Application URL | `cis.yourdomain.com` (your subdomain) |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

3. Click **Create** — cPanel creates `~/vcdp-cis/` and a virtual environment

---

## STEP 4 — Upload project files

### Via File Manager:
1. cPanel → **File Manager** → navigate to your home directory (`/home/USERNAME/`)
2. Upload `vcdp-cis-system.zip` into the `vcdp-cis/` folder
3. Right-click the zip → **Extract** (extract here, inside `vcdp-cis/`)
4. If files land in a subfolder (e.g. `vcdp-cis/vcdp-cis/`), move them up one level

### Via SSH (faster):
```bash
cd ~/vcdp-cis
# Upload the zip via SFTP first, then:
unzip -o vcdp-cis-system.zip
# If files landed in a subfolder:
mv vcdp-cis/* . 2>/dev/null; rmdir vcdp-cis 2>/dev/null
```

### Verify your structure looks like this:
```
~/vcdp-cis/
  app.py
  config.py
  models.py
  passenger_wsgi.py
  requirements.txt
  requirements-postgres.txt
  .env
  routes/
  services/
  seeds/
  templates/
  static/
```

---

## STEP 5 — Create MySQL Database

cPanel shared hosting uses MySQL (not PostgreSQL):

1. cPanel → **MySQL Databases**
2. **Create Database**: `vcdp_cis_db`  
   *(Full name will be `CPANELUSERNAME_vcdp_cis_db`)*
3. **Create User**: `vcdp_user` with a strong password (save this!)
4. **Add User To Database** → select both → grant **ALL PRIVILEGES**

---

## STEP 6 — Configure environment variables

### Option A — via cPanel Setup Python App:
Click your app → **Environment Variables** → add each row:

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | `vcdp-prod-2026-GreenAllied-NoblEn!` *(change this)* |
| `DATABASE_URL` | `mysql+pymysql://CPANELUSERNAME_vcdp_user:PASSWORD@localhost/CPANELUSERNAME_vcdp_cis_db` |
| `FLASK_ENV` | `production` |
| `NO_SCHEDULER` | `1` |
| `TERMII_API_KEY` | `TLNTscjMCFrXMfiPFvOUwbaIrwXkMsDaeTCajhJsBhCGYEPBehPWTnJYIOywmW` |
| `SENDER_ID` | `VCDP` |
| `SMS_COST_KOBO` | `600` |
| `TUYA_CLIENT_ID` | *(leave blank until weather stations are set up)* |
| `TUYA_CLIENT_SECRET` | *(leave blank until weather stations are set up)* |
| `TUYA_DATA_CENTER` | `eu` |

### Option B — edit `.env` file directly via File Manager:
Open `~/vcdp-cis/.env` and update each line:
```
SECRET_KEY=vcdp-prod-2026-GreenAllied-NoblEn!
DATABASE_URL=mysql+pymysql://CPANELUSERNAME_vcdp_user:PASSWORD@localhost/CPANELUSERNAME_vcdp_cis_db
FLASK_ENV=production
NO_SCHEDULER=1
TERMII_API_KEY=TLNTscjMCFrXMfiPFvOUwbaIrwXkMsDaeTCajhJsBhCGYEPBehPWTnJYIOywmW
SENDER_ID=VCDP
SMS_COST_KOBO=600
TUYA_DATA_CENTER=eu
```

> ⚠️ Replace `CPANELUSERNAME`, `vcdp_user`, and `PASSWORD` with your actual values.

---

## STEP 7 — Install dependencies via SSH

```bash
# 1. Activate the virtual environment cPanel created
source ~/virtualenv/vcdp-cis/3.11/bin/activate

# 2. Go to project folder
cd ~/vcdp-cis

# 3. Add PyMySQL for MySQL support (run this once)
echo "PyMySQL==1.1.0" >> requirements.txt

# 4. Install all dependencies
pip install -r requirements.txt

# 5. Confirm Flask is installed
python -c "import flask; print('Flask', flask.__version__)"
```

Expected output: `Flask 3.0.0`

---

## STEP 8 — Initialize the database via SSH

```bash
# Still in the activated virtualenv from Step 7:
cd ~/vcdp-cis

# Set env vars for this session
export FLASK_APP=app.py
export $(cat .env | grep -v '^#' | xargs)

# Create all tables and run migrations
flask db upgrade

# If flask db upgrade fails (first time, no migrations folder):
flask db init
flask db migrate -m "initial"
flask db upgrade
```

You should see output like:
```
INFO  [alembic] Running upgrade  -> abc123, initial
```

The first time the app starts it will also auto-seed:
- ✅ 11 admin accounts (1 owner + 1 NPMU + 9 SPMU)
- ✅ 17 SMS templates
- ✅ Programme LGAs for all 9 states

---

## STEP 9 — Restart the application

cPanel → **Setup Python App** → find your app → click **Restart**

Then visit: `https://cis.yourdomain.com`

You should see the VCDP CIDU login page.

---

## STEP 10 — Verify it's working

Visit: `https://cis.yourdomain.com/api/health`

Expected response:
```json
{"status": "ok", "service": "VCDP CIDU"}
```

Then log in:
```
Username: yusufyau
Password: VCDP@Owner2026!
```

---

## STEP 11 — Set up Cron Jobs (replaces background scheduler)

Since `NO_SCHEDULER=1` on shared hosting, set up cPanel Cron Jobs to send
weather SMS alerts every Monday and Thursday at 7:00 AM WAT (6:00 AM UTC):

cPanel → **Cron Jobs** → **Add New Cron Job**:

```
Minute: 0
Hour:   6
Day:    *
Month:  *
Weekday: 1,4

Command:
source ~/virtualenv/vcdp-cis/3.11/bin/activate && cd ~/vcdp-cis && export $(cat .env | grep -v '^#' | xargs) && flask trigger-broadcast >> ~/logs/vcdp-cron.log 2>&1
```

Create the log folder first:
```bash
mkdir -p ~/logs
```

---

## STEP 12 — SSL Certificate (HTTPS)

1. cPanel → **SSL/TLS** → **AutoSSL** (free Let's Encrypt)
2. Click **Run AutoSSL** — certificates install automatically for your subdomain
3. Done — your site will be `https://`

---

## Login Credentials Summary

| Role | Username | Password | Access |
|------|----------|----------|--------|
| **Programme Administrator** | `yusufyau` | `VCDP@Owner2026!` | Full — all states |
| **NPMU Admin** | `npmu_admin` | `VCDP@Npmu2026!` | Full — all states |
| Anambra SPMU | `spmu_anambra` | `VCDP@Anambra2026!` | Anambra only |
| Benue SPMU | `spmu_benue` | `VCDP@Benue2026!` | Benue only |
| Ebonyi SPMU | `spmu_ebonyi` | `VCDP@Ebonyi2026!` | Ebonyi only |
| Enugu SPMU | `spmu_enugu` | `VCDP@Enugu2026!` | Enugu only |
| Kogi SPMU | `spmu_kogi` | `VCDP@Kogi2026!` | Kogi only |
| Nasarawa SPMU | `spmu_nasarawa` | `VCDP@Nasarawa2026!` | Nasarawa only |
| Niger SPMU | `spmu_niger` | `VCDP@Niger2026!` | Niger only |
| Ogun SPMU | `spmu_ogun` | `VCDP@Ogun2026!` | Ogun only |
| Taraba SPMU | `spmu_taraba` | `VCDP@Taraba2026!` | Taraba only |

> 🔒 Share SPMU credentials securely (WhatsApp or Signal, not email).
> Change all passwords after first login.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Login page shows but login fails | Check `SECRET_KEY` is set in env vars |
| `500 Internal Server Error` | Check cPanel → **Metrics** → **Error Logs** |
| `ModuleNotFoundError: flask` | Re-run `pip install -r requirements.txt` in the activated venv |
| `Access denied for user` MySQL error | Recheck `DATABASE_URL` — username and DB name must include the cPanel username prefix |
| App loads but shows blank dashboard | Hard refresh `Ctrl+Shift+R` — clears cached broken JS |
| `flask db upgrade` fails with "No module named flask_migrate" | Run pip install again — virtualenv may not be activated |
| Passenger error / 503 | Check `passenger_wsgi.py` exists in the app root; restart the app |
| Cron job not running | Check `~/logs/vcdp-cron.log` for errors; ensure venv path is correct |

---

## Appendix A — SSH-only setup (if Setup Python App not available)

If your cPanel doesn't have Setup Python App, use this method:

```bash
# SSH into your server
ssh USERNAME@YOUR_SERVER_IP

# Install Python 3.11 in user space (if not available system-wide)
cd ~
python3 --version   # check what's available

# Create virtualenv manually
python3 -m venv ~/virtualenv/vcdp-cis
source ~/virtualenv/vcdp-cis/bin/activate

# Upload and extract files
cd ~
unzip vcdp-cis-system.zip
# (files go to ~/vcdp-cis/)

# Install dependencies + PyMySQL
cd ~/vcdp-cis
pip install -r requirements.txt
pip install PyMySQL==1.1.0

# Set up .env (edit with nano)
nano .env

# Initialize database
export FLASK_APP=app.py
flask db upgrade

# Create .htaccess for Passenger
cat > ~/public_html/.htaccess << 'HTACCESS'
PassengerEnabled On
PassengerAppRoot /home/USERNAME/vcdp-cis
PassengerBaseURI /
PassengerPython /home/USERNAME/virtualenv/vcdp-cis/bin/python3
HTACCESS
```

---

*Generated by Noblen Technologies Limited for Green Allied Trust Nig. Ltd / IFAD-VCDP CIDU Programme*
