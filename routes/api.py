import csv, io, re
from flask import Blueprint, request, jsonify, send_file, render_template
from flask_login import login_required, current_user
from models import db, Participant, SMSLog, Template, WeatherCache, DashboardMetric, WeatherStation, ProgrammeLGA, User, FieldReport, AdvisoryFeedback
from services.sms_gateway import send_sms, check_balance, test_connection
from services.weather_api import get_weather_for_lga, LGA_COORDS, load_lga_coordinates
from services import tuya_client
from datetime import datetime, date
from config import Config
import logging

logger = logging.getLogger(__name__)
api = Blueprint("api", __name__)

# Roles whose data access is limited to their assigned state
STATE_SCOPED = ("spmu", "extension_agent", "climate_champion")

# ── Utilities ──────────────────────────────────────────────────────────────
def clean_phone(raw):
    """
    Normalize any common Nigerian phone input into the canonical storage
    format used everywhere in this system: 234XXXXXXXXXX (13 digits, no +,
    no leading 0). Handles all of the following input styles people actually
    type or paste from Excel:
        08012345678        -> 2348012345678
        8012345678          -> 2348012345678   (missing leading 0)
        +2348012345678      -> 2348012345678
        2348012345678        -> 2348012345678
        234 801 234 5678     -> 2348012345678  (spaces/dashes/dots stripped)
        +234 (0)801 234 5678 -> 2348012345678  (parenthesised 0 after code)
        2340801...            -> 2348012345678  (0 mistakenly kept after 234)
    Returns None if the result isn't a plausible 13-digit Nigerian number.
    """
    if not raw:
        return None
    p = re.sub(r"[^\d]", "", str(raw).strip())  # strip +, spaces, dashes, dots, brackets
    if not p:
        return None

    # Country code present but a stray 0 was kept right after it (2340801...)
    if p.startswith("2340") and len(p) == 14:
        p = "234" + p[4:]
    # Standard local format: 0 + 10 digits
    elif p.startswith("0") and len(p) == 11:
        p = "234" + p[1:]
    # Already has country code, correct length
    elif p.startswith("234") and len(p) == 13:
        pass
    # Bare 10-digit number with no leading 0 and no country code (e.g. "8012345678")
    elif len(p) == 10 and not p.startswith("0"):
        p = "234" + p
    # Country code with no leading 0 needed but extra/missing digit noise — try a
    # last-resort trim/pad using the trailing 10 digits as the subscriber number
    elif len(p) >= 10:
        tail = p[-10:]
        if tail[0] in "789":  # Nigerian mobile numbers start with 7, 8, or 9
            p = "234" + tail
        else:
            return None
    else:
        return None

    return p if len(p) == 13 and p.startswith("234") and p[3] in "789" else None

def upsert_metric(name, value, state=None, lga=None):
    m = DashboardMetric.query.filter_by(metric_name=name,state=state,lga=lga).first()
    if m: m.metric_value=value; m.recorded_at=datetime.utcnow()
    else: db.session.add(DashboardMetric(metric_name=name,metric_value=value,state=state,lga=lga))
    db.session.commit()

def next_bid(state):
    abbr = state.replace(" State","").replace(" ","")[:3].upper()
    return f"VCDP-{abbr}-{Participant.query.filter_by(state=state).count()+1:03d}"

def get_state_lgas(state):
    """Database-backed programme LGA list for a state (Owner/NPMU manage this via the UI)."""
    rows = ProgrammeLGA.query.filter_by(state=state).order_by(ProgrammeLGA.lga).all()
    return [r.lga for r in rows]

def get_all_state_lgas():
    """Full {state: [lgas]} map, database-backed."""
    out = {s: [] for s in Config.VALID_STATES}
    for row in ProgrammeLGA.query.order_by(ProgrammeLGA.state, ProgrammeLGA.lga).all():
        out.setdefault(row.state, []).append(row.lga)
    return out

def _get_template(role, lang="en"):
    t = Template.query.filter_by(language=lang,  crop=role).first() if role else None
    t = t or Template.query.filter_by(language=lang,  crop="general").first()
    t = t or Template.query.filter_by(language="en",  crop="general").first()
    return t

def _build_message(template, weather):
    return template.content.format(
        rain=round(weather.rainfall_mm or 0,1),
        temp=round(weather.max_temp_c  or 0,1),
        alert=weather.alert or "No alerts")

# ── Health ─────────────────────────────────────────────────────────────────
@api.route("/api/health")
def health():
    return jsonify({"status":"ok","service":"VCDP CIDU","version":"1.0"})

# ── Dashboard ──────────────────────────────────────────────────────────────
@api.route("/")
@login_required
def dashboard():
    return render_template("index.html",
        username=current_user.username, role=current_user.role, user_state=current_user.state,
        user_supplier=current_user.supplier)

@api.route("/api/stats")
@login_required
def get_stats():
    scope = current_user.state if current_user.role in STATE_SCOPED else None
    def q(): b=Participant.query; return b.filter_by(state=scope) if scope else b
    total     = q().count()
    verified  = q().filter_by(phone_verified=True).count()
    onboarded = q().filter_by(cis_onboarded=True).count()
    consented = q().filter_by(opted_in=True).count()
    active    = q().filter_by(status="Active").count()
    pwd_count = q().filter_by(pwd_status=True).count()
    # "AWS Coverage" = beneficiaries located in an LGA that has an ACTIVE
    # registered Tuya FJ3395 Automatic Weather Station (real station coverage,
    # not the old unused aws_cluster boolean flag).
    active_station_lgas = db.session.query(WeatherStation.state, WeatherStation.lga)\
        .filter_by(status="active").distinct().all()
    if active_station_lgas:
        aws_filter = db.or_(*[
            db.and_(Participant.state == s, Participant.lga == l)
            for s, l in active_station_lgas
        ])
        aws_count = q().filter(aws_filter).count()
    else:
        aws_count = 0
    if scope:
        sms_q = db.session.query(SMSLog).join(Participant,SMSLog.participant_id==Participant.id).filter(Participant.state==scope)
    else:
        sms_q = SMSLog.query
    total_sms = sms_q.count()
    ok_sms    = sms_q.filter(SMSLog.status=="success").count()
    fail_sms  = sms_q.filter(SMSLog.status=="failed").count()
    today_start = datetime.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)
    today_sms   = sms_q.filter(SMSLog.sent_at>=today_start).count()
    male   = q().filter_by(gender="Male").count()
    female = q().filter_by(gender="Female").count()
    young_male   = q().filter(Participant.gender=="Male",   Participant.age_group=="15-35").count()
    young_female = q().filter(Participant.gender=="Female", Participant.age_group=="15-35").count()
    role_stats  = {r: q().filter_by(role=r).count() for r in Config.VALID_CATEGORIES}
    crop_stats  = {c: q().filter_by(primary_crop=c).count() for c in Config.VALID_CROPS}
    age_stats   = {a: q().filter_by(age_group=a).count() for a in Config.VALID_AGE_GROUPS}
    lang_stats  = {l: q().filter_by(language_pref=l).count() for l in Config.VALID_LANGUAGES}
    visible     = [scope] if scope else Config.VALID_STATES
    state_stats = [{"state":s,"total":Participant.query.filter_by(state=s).count(),
                    "onboarded":Participant.query.filter_by(state=s,cis_onboarded=True).count()}
                   for s in visible]
    lgas_q = db.session.query(Participant.lga)
    if scope: lgas_q = lgas_q.filter(Participant.state==scope)
    agents_q    = User.query.filter_by(role="extension_agent")
    champions_q = User.query.filter_by(role="climate_champion")
    if scope:
        agents_q    = agents_q.filter_by(state=scope)
        champions_q = champions_q.filter_by(state=scope)
    stations_q = WeatherStation.query
    if current_user.role == "aws_supplier":
        stations_q = stations_q.filter_by(supplier=current_user.supplier)
    elif scope:
        stations_q = stations_q.filter_by(state=scope)
    stations_total   = stations_q.count()
    stations_online  = stations_q.filter_by(is_online=True).count()
    stations_offline = stations_q.filter(WeatherStation.is_online.isnot(True)).count()
    return jsonify({
        "total_participants":scope and total or Participant.query.count(),
        "numbers_verified":verified,"cis_onboarded":onboarded,
        "opted_in_sms":consented,"active_beneficiaries":active,
        "pwd_count":pwd_count,"aws_cluster_count":aws_count,
        "total_sms_sent":total_sms,"successful_sms":ok_sms,
        "failed_sms":fail_sms,"today_sms":today_sms,
        "states_covered":1 if scope else db.session.query(Participant.state).distinct().count(),
        "lgas_covered":lgas_q.distinct().count(),
        "extension_agents":agents_q.count(),
        "climate_champions":champions_q.count(),
        "stations_total":stations_total,"stations_online":stations_online,"stations_offline":stations_offline,
        "gender":{"male":male,"female":female,"young_male":young_male,"young_female":young_female},
        "by_role":role_stats,"by_crop":crop_stats,"by_age":age_stats,"by_language":lang_stats,
        "by_state":state_stats,
        "sms_balance": check_balance() if current_user.role in ("owner","admin") else None
    })

# ── Location APIs ──────────────────────────────────────────────────────────
@api.route("/api/states")
@login_required
def get_states():
    return jsonify({"states":Config.VALID_STATES})

@api.route("/api/lgas")
@login_required
def get_lgas():
    state = request.args.get("state","").strip()
    return jsonify({"lgas": get_state_lgas(state)})

# ── CSV Import ─────────────────────────────────────────────────────────────
@api.route("/download_template")
@login_required
def download_template():
    h = ("FULL_NAME,GENDER,AGE_GROUP,PHONE_PRIMARY,PWD_STATUS,ROLE,"
         "STATE,LGA,CLUSTER,PRIMARY_CROP,FO_GROUP_NAME,LANGUAGE_PREF,"
         "OPTED_IN_SMS,CIS_ONBOARDED,WHATSAPP_CONTACT,EXTENSION_AGENT,CLIMATE_CHAMPION")
    ex1 = ("Amina Bello,Female,15-35,08012345678,No,Producer,"
           "Niger State,Mokwa,Mokwa Rice Hub,Rice,Mokwa FGA,en,Yes,Yes,08012345678,Musa Ibrahim,Hauwa Sani")
    ex2 = ("Musa Garba,Male,35-Above,08023456789,No,Processor,"
           "Benue State,Logo,Logo Processing Cluster,Cassava,Logo Cooperative,ha,Yes,No,08098765432,,")
    return send_file(io.BytesIO((h+"\n"+ex1+"\n"+ex2+"\n").encode()), mimetype="text/csv",
                     as_attachment=True, download_name="vcdp_cidu_beneficiary_template.csv")

@api.route("/download_template_xlsx")
@login_required
def download_template_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Beneficiaries"

    headers = ["FULL_NAME","GENDER","AGE_GROUP","PHONE_PRIMARY","PWD_STATUS","ROLE",
               "STATE","LGA","CLUSTER","PRIMARY_CROP","FO_GROUP_NAME","LANGUAGE_PREF",
               "OPTED_IN_SMS","CIS_ONBOARDED","WHATSAPP_CONTACT","EXTENSION_AGENT","CLIMATE_CHAMPION"]
    ws.append(headers)
    for col in range(1, len(headers)+1):
        c = ws.cell(row=1, column=col)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="008B8B")
        c.alignment = Alignment(horizontal="center")

    ws.append(["Amina Bello","Female","15-35","08012345678","No","Producer",
                "Niger State","Mokwa","Mokwa Rice Hub","Rice","Mokwa FGA","en","Yes","Yes",
                "08012345678","Musa Ibrahim","Hauwa Sani"])
    ws.append(["Musa Garba","Male","35-Above","08023456789","No","Processor",
                "Benue State","Logo","Logo Processing Cluster","Cassava","Logo Cooperative","ha","Yes","No",
                "08098765432","",""])

    widths = [22,10,12,16,11,12,16,14,22,12,22,12,12,14,17,20,20]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1,column=i).column_letter].width = w

    # Dropdown validations
    # Columns: A FULL_NAME, B GENDER, C AGE_GROUP, D PHONE_PRIMARY, E PWD_STATUS, F ROLE,
    #          G STATE, H LGA, I CLUSTER (free text, no dropdown), J PRIMARY_CROP,
    #          K FO_GROUP_NAME, L LANGUAGE_PREF, M OPTED_IN_SMS, N CIS_ONBOARDED,
    #          O WHATSAPP_CONTACT (phone, free text), P EXTENSION_AGENT (free text),
    #          Q CLIMATE_CHAMPION (free text)
    dv_gender = DataValidation(type="list", formula1='"Male,Female"', allow_blank=True)
    dv_age    = DataValidation(type="list", formula1='"15-35,35-Above"', allow_blank=True)
    dv_role   = DataValidation(type="list", formula1='"Producer,Processor,Marketer"', allow_blank=True)
    dv_crop   = DataValidation(type="list", formula1='"Rice,Cassava"', allow_blank=True)
    dv_yesno  = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    dv_lang   = DataValidation(type="list", formula1='"en,ha,ig,yo,pcm,nup"', allow_blank=True)
    dv_state  = DataValidation(type="list", formula1='"'+",".join(Config.VALID_STATES)+'"', allow_blank=True)

    for dv in (dv_gender,dv_age,dv_role,dv_crop,dv_yesno,dv_lang,dv_state):
        ws.add_data_validation(dv)

    dv_gender.add("B2:B1000"); dv_age.add("C2:C1000")
    dv_yesno.add("E2:E1000")
    dv_role.add("F2:F1000"); dv_state.add("G2:G1000")
    dv_crop.add("J2:J1000"); dv_lang.add("L2:L1000")
    dv_yesno.add("M2:M1000"); dv_yesno.add("N2:N1000")

    # LGA reference sheet (since LGA depends on State, can't do a simple dropdown chain in plain xlsx)
    ref = wb.create_sheet("Valid LGAs by State")
    ref.append(["STATE","PROGRAMME LGAs"])
    for c in (1,2):
        cell = ref.cell(row=1,column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="006666")
    for state, lgas in get_all_state_lgas().items():
        ref.append([state, ", ".join(lgas) if lgas else "(no LGAs configured yet)"])
    ref.column_dimensions["A"].width = 18
    ref.column_dimensions["B"].width = 70

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="vcdp_cidu_beneficiary_template.xlsx")

@api.route("/import_csv", methods=["POST"])
@login_required
def import_csv():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error":"Please choose a file to upload (.csv, .xlsx, or .xls)"}), 400

    fname = file.filename.lower()
    results = {"success":0,"skipped":0,"errors":[]}

    # ── Read rows generically from CSV or Excel ─────────────────────────
    rows = []
    fieldnames = []
    if fname.endswith(".csv"):
        raw = file.stream.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("latin-1")
            except Exception as e:
                return jsonify({"error": f"Could not read file encoding: {e}"}), 400
        stream = io.StringIO(text, newline=None)
        reader = csv.DictReader(stream)
        fieldnames = [ (h or "").strip().upper() for h in (reader.fieldnames or []) ]
        for row in reader:
            rows.append({ (k or "").strip().upper(): v for k, v in row.items() })

    elif fname.endswith(".xlsx") or fname.endswith(".xls"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            return jsonify({"error":"Server is missing the 'openpyxl' package required to read Excel files. "
                                     "Please install it (pip install openpyxl) or upload a .csv file instead."}), 500
        try:
            wb = load_workbook(file.stream, data_only=True, read_only=True)
        except Exception as e:
            return jsonify({"error": f"Could not read Excel file: {e}. Try saving as .csv instead."}), 400

        ws = wb.worksheets[0]  # first sheet only
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return jsonify({"error":"The selected sheet appears to be empty."}), 400
        fieldnames = [ (str(h).strip().upper() if h is not None else "") for h in header_row ]
        for raw_row in rows_iter:
            row = {}
            for idx, val in enumerate(raw_row):
                if idx < len(fieldnames) and fieldnames[idx]:
                    row[fieldnames[idx]] = "" if val is None else str(val)
            if any(v.strip() for v in row.values()):
                rows.append(row)
    else:
        return jsonify({"error":"Unsupported file type. Please upload a .csv, .xlsx, or .xls file."}), 400

    if "PHONE_PRIMARY" not in fieldnames or "FULL_NAME" not in fieldnames:
        return jsonify({"error":"Required columns not found. Your file must include at least "
                                 "FULL_NAME and PHONE_PRIMARY columns. Use the Download Template "
                                 "button to get the correct format.",
                         "found_headers": fieldnames}), 400

    # Pre-load all existing phone numbers once (avoids 1 query per row)
    existing_phones = {p[0] for p in db.session.query(Participant.phone).all()}
    seen_phones = set()

    BATCH_SIZE = 200
    pending = 0
    today_str = date.today().isoformat()
    all_state_lgas = get_all_state_lgas()  # pre-load once, not per-row

    def tb(v, default=False):
        v = str(v).strip().lower()
        if v in ("yes","true","1"): return True
        if v in ("no","false","0",""): return False if not default else True
        return default

    for i, row in enumerate(rows, start=2):
        try:
            full_name = (row.get("FULL_NAME") or "").strip()
            if not full_name:
                continue  # silently skip fully blank rows

            phone = clean_phone(row.get("PHONE_PRIMARY",""))
            if not phone:
                results["errors"].append(f"Row {i}: Invalid or missing phone number")
                continue
            if phone in existing_phones or phone in seen_phones:
                results["skipped"] += 1
                continue

            state = (row.get("STATE") or "").strip()
            if state not in Config.VALID_STATES:
                results["errors"].append(f"Row {i}: State '{state}' not recognised")
                continue
            if current_user.role in STATE_SCOPED and state != current_user.state:
                results["errors"].append(f"Row {i}: You can only import beneficiaries for {current_user.state} "
                                          f"(row has '{state}')")
                continue

            lga = (row.get("LGA") or "").strip().title()
            valid_lgas = all_state_lgas.get(state, [])
            if lga not in valid_lgas:
                results["errors"].append(f"Row {i}: LGA '{lga}' not valid for {state} "
                                          f"(valid: {', '.join(valid_lgas) if valid_lgas else 'none configured yet'})")
                continue

            role = (row.get("ROLE") or "").strip().title()
            if role not in Config.VALID_CATEGORIES:
                results["errors"].append(f"Row {i}: ROLE '{role}' must be Producer, Processor or Marketer")
                continue

            crop = (row.get("PRIMARY_CROP") or "").strip().title()
            if crop and crop not in Config.VALID_CROPS:
                results["errors"].append(f"Row {i}: PRIMARY_CROP '{crop}' must be Rice or Cassava")
                continue

            gender = (row.get("GENDER") or "").strip().title()
            age_group = (row.get("AGE_GROUP") or "").strip()
            # Normalise common alternative age inputs to the two-band scheme
            if age_group not in Config.VALID_AGE_GROUPS:
                age_group_l = age_group.lower().replace(" ","")
                if age_group_l in ("youth","15-25","26-35","15to35","young"):
                    age_group = "15-35"
                elif age_group_l in ("adult","36-45","46-55","56-65","65+","old","35above","35+"):
                    age_group = "35-Above"
                else:
                    age_group = "15-35"  # safe default

            opted_in = tb(row.get("OPTED_IN_SMS"), default=True)
            onboarded = tb(row.get("CIS_ONBOARDED"), default=False)
            wa_raw = (row.get("WHATSAPP_CONTACT") or "").strip()
            wa_phone = clean_phone(wa_raw) if wa_raw else None

            db.session.add(Participant(
                beneficiary_id=(row.get("BENEFICIARY_ID") or "").strip() or next_bid(state),
                full_name=full_name.title(),
                gender=gender or None,
                age_group=age_group,
                phone=phone,
                whatsapp_contact=wa_phone,
                extension_agent=(row.get("EXTENSION_AGENT") or "").strip() or None,
                climate_champion=(row.get("CLIMATE_CHAMPION") or "").strip() or None,
                pwd_status=tb(row.get("PWD_STATUS"), default=False),
                role=role,
                state=state, lga=lga,
                cluster=(row.get("CLUSTER") or "").strip() or None,
                fo_group=(row.get("FO_GROUP_NAME") or "").strip() or None,
                primary_crop=crop or None,
                language_pref=(row.get("LANGUAGE_PREF") or "en").strip().lower() or "en",
                opted_in=opted_in,
                consent_date=date.today() if opted_in else None,
                cis_onboarded=onboarded,
                onboarding_date=datetime.utcnow() if onboarded else None,
                phone_verified=onboarded,  # onboarded implies already verified
                registration_source="SPMU Upload",
                data_protection_consent=True,
                status="Active",
                updated_by=current_user.username))

            seen_phones.add(phone)
            results["success"] += 1
            pending += 1

            if pending >= BATCH_SIZE:
                db.session.commit()
                pending = 0

        except Exception as e:
            results["errors"].append(f"Row {i}: {e}")
            db.session.rollback()

    if pending:
        db.session.commit()

    upsert_metric("total_participants", Participant.query.count())

    # Cap error list shown to client (full count still accurate)
    results["error_count"] = len(results["errors"])
    if len(results["errors"]) > 50:
        results["errors"] = results["errors"][:50] + [f"... and {len(results['errors'])-50} more errors"]

    return jsonify(results)


# ── Verify Phones ──────────────────────────────────────────────────────────
@api.route("/verify_phones", methods=["POST"])
@login_required
def verify_phones():
    state = request.form.get("state","").strip()
    lga   = request.form.get("lga","").strip().title()
    role  = request.form.get("role","").strip().title()
    if current_user.role in STATE_SCOPED and state and state != current_user.state:
        return jsonify({"error":"You can only manage beneficiaries for your own state"}), 403
    if current_user.role in STATE_SCOPED and not state:
        state = current_user.state
    q = Participant.query.filter_by(opted_in=True, phone_verified=False)
    if state: q=q.filter_by(state=state)
    if lga:   q=q.filter_by(lga=lga)
    if role:  q=q.filter_by(role=role)
    targets = q.all(); verified=failed=0
    for p in targets:
        res = send_sms(p.phone,"VCDP CIDU: Reply YES to confirm this number for weather alerts. Reply STOP to opt out.")
        if res["status"] in ("success","simulated"):
            p.phone_verified=True; p.verification_date=datetime.utcnow()
            p.cis_onboarded=True; p.onboarding_date=datetime.utcnow()
            p.verification_method="SMS"; verified+=1
        else: failed+=1
        db.session.add(SMSLog(participant_id=p.id,message="Verification SMS",
            status=res["status"],gateway_id=res.get("gateway_id"),cost_kobo=res.get("cost_kobo",0)))
    db.session.commit()
    return jsonify({"verified":verified,"failed":failed,"total_attempted":len(targets)})

# ── Weather SMS ────────────────────────────────────────────────────────────
@api.route("/preview", methods=["POST"])
@login_required
def preview_sms():
    state = request.form.get("state","").strip()
    lga   = request.form.get("lga","").strip().title()
    role  = request.form.get("role","").strip().title()
    lang  = request.form.get("lang","en").strip().lower()
    if current_user.role in STATE_SCOPED and state != current_user.state:
        return "You can only manage beneficiaries for your own state", 403
    weather  = get_weather_for_lga(state, lga)
    if not weather: return f"Weather data unavailable for {lga}, {state}", 400
    template = _get_template(role, lang)
    if not template: return "No SMS template configured. Initialize templates first.", 404
    message = _build_message(template, weather)
    q = Participant.query.filter_by(state=state, lga=lga, cis_onboarded=True)
    if role: q=q.filter_by(role=role)
    count = q.count()
    lmap = {"en":"English","ha":"Hausa","ig":"Igbo","yo":"Yoruba","pcm":"Pidgin"}
    out = (f"MESSAGE PREVIEW\n{'='*40}\n{message}\n{'='*40}\n\n"
           f"Target: {lga}, {state}\nRole: {role or 'All'}\nLanguage: {lmap.get(lang,lang)}\n"
           f"Onboarded recipients: {count:,}")
    if current_user.role in ("owner","admin"):
        out += f"\nRate: NGN {Config.SMS_COST_KOBO/100:.2f}/SMS"
    return out

@api.route("/send_weather", methods=["POST"])
@login_required
def send_weather_sms():
    state = request.form.get("state","").strip()
    lga   = request.form.get("lga","").strip().title()
    role  = request.form.get("role","").strip().title()
    lang  = request.form.get("lang","en").strip().lower()
    if current_user.role in STATE_SCOPED and state != current_user.state:
        return jsonify({"error":"You can only manage beneficiaries for your own state"}), 403
    weather  = get_weather_for_lga(state, lga)
    if not weather: return jsonify({"error":f"Weather data unavailable for {lga}, {state}"}),400
    template = _get_template(role, lang)
    if not template: return jsonify({"error":"No template found. Initialize templates first."}),404
    message = _build_message(template, weather)
    q = Participant.query.filter_by(state=state, lga=lga, cis_onboarded=True)
    if role: q=q.filter_by(role=role)
    targets = q.all(); success_count=failed_count=total_cost=0; logs=[]
    for p in targets:
        res = send_sms(p.phone, message)
        logs.append(SMSLog(participant_id=p.id,message=message,status=res["status"],
            gateway_id=res.get("gateway_id"),cost_kobo=res.get("cost_kobo",0)))
        total_cost+=res.get("cost_kobo",0)
        if res["status"] in ("success","simulated"): success_count+=1
        else: failed_count+=1
    db.session.add_all(logs); db.session.commit()
    upsert_metric("total_sms_sent",SMSLog.query.count())
    upsert_metric("successful_sms",SMSLog.query.filter_by(status="success").count())
    resp = {"sent":len(targets),"successful":success_count,"failed":failed_count,
        "message_preview":message[:120]+("..." if len(message)>120 else "")}
    if current_user.role in ("owner","admin"):
        resp["total_cost_kobo"] = total_cost
        resp["total_cost_naira"] = round(total_cost/100,2)
    return jsonify(resp)

@api.route("/whatsapp_broadcast", methods=["POST"])
@login_required
def whatsapp_broadcast():
    """
    Weather WhatsApp dispatch — builds the same localized weather advisory as
    Weather SMS, but instead of sending through the SMS gateway it returns the
    advisory plus the matched opted-in recipients so the dashboard can render
    per-recipient wa.me chat links and a copy-ready broadcast list.
    preview=1 returns only the advisory text (no recipients, nothing logged).
    """
    state   = request.form.get("state","").strip()
    lga     = request.form.get("lga","").strip().title()
    role    = request.form.get("role","").strip().title()
    lang    = request.form.get("lang","en").strip().lower()
    preview = request.form.get("preview","0") == "1"
    if current_user.role in STATE_SCOPED and state != current_user.state:
        return jsonify({"error":"You can only manage beneficiaries for your own state"}), 403
    if not state or not lga:
        return jsonify({"error":"State and LGA are required"}), 400
    weather = get_weather_for_lga(state, lga)
    if not weather: return jsonify({"error":f"Weather data unavailable for {lga}, {state}"}), 400
    template = _get_template(role, lang)
    if not template: return jsonify({"error":"No template found. Initialize templates first."}), 404
    message = _build_message(template, weather)[:306]
    if preview:
        return jsonify({"message": message, "characters": len(message)})
    q = Participant.query.filter_by(state=state, lga=lga, cis_onboarded=True)
    if role: q = q.filter_by(role=role)
    targets = q.all()
    recipients = [{"name": p.full_name, "phone": (p.whatsapp_contact or p.phone)} for p in targets]
    # Log dispatch (cost 0 — delivered via WhatsApp, not the SMS gateway)
    logs = [SMSLog(participant_id=p.id, message="[WHATSAPP] "+message,
                   status="whatsapp", cost_kobo=0) for p in targets]
    db.session.add_all(logs); db.session.commit()
    return jsonify({"message": message, "characters": len(message),
                    "count": len(recipients), "recipients": recipients})

@api.route("/broadcast", methods=["POST"])
@login_required
def broadcast_weather_sms():
    lang = request.form.get("lang","en").strip().lower()
    scope = current_user.state if current_user.role in STATE_SCOPED else None
    q = db.session.query(Participant.state,Participant.lga).filter_by(cis_onboarded=True)
    if scope: q=q.filter(Participant.state==scope)
    pairs = q.distinct().all()
    if not pairs: return jsonify({"error":"No onboarded beneficiaries found"}),404
    total_sent=total_success=total_failed=total_cost=0; skipped=[]; dispatched=[]
    for state, lga in pairs:
        weather = get_weather_for_lga(state, lga)
        if not weather: skipped.append(f"{lga}, {state}"); continue
        for role in Config.VALID_CATEGORIES:
            template = _get_template(role, lang)
            if not template: continue
            message = _build_message(template, weather)
            for p in Participant.query.filter_by(state=state,lga=lga,cis_onboarded=True,role=role).all():
                res = send_sms(p.phone, message)
                db.session.add(SMSLog(participant_id=p.id,message=message,status=res["status"],
                    gateway_id=res.get("gateway_id"),cost_kobo=res.get("cost_kobo",0)))
                total_cost+=res.get("cost_kobo",0); total_sent+=1
                if res["status"] in ("success","simulated"): total_success+=1
                else: total_failed+=1
        dispatched.append(f"{lga}, {state}")
    db.session.commit()
    upsert_metric("total_sms_sent",SMSLog.query.count())
    lmap = {"en":"English","ha":"Hausa","ig":"Igbo","yo":"Yoruba","pcm":"Pidgin"}
    resp = {"total_sent":total_sent,"successful":total_success,"failed":total_failed,
        "lgas_reached":len(dispatched),"lgas_skipped":len(skipped),"skipped_list":skipped,
        "language":lmap.get(lang,lang),"scope":scope or "All 9 States"}
    if current_user.role in ("owner","admin"):
        resp["total_cost_kobo"] = total_cost
        resp["total_cost_naira"] = round(total_cost/100,2)
    return jsonify(resp)

# ── Export ─────────────────────────────────────────────────────────────────
@api.route("/export_logs")
@login_required
def export_logs():
    fs=request.args.get("state","").strip(); fl=request.args.get("lga","").strip().title()
    if current_user.role in STATE_SCOPED:
        fs = current_user.state  # SPMU can only export their own state's logs
    q = db.session.query(SMSLog,Participant).join(Participant,SMSLog.participant_id==Participant.id)
    if fs: q=q.filter(Participant.state==fs)
    if fl: q=q.filter(Participant.lga==fl)
    buf=io.StringIO(); w=csv.writer(buf)
    w.writerow(["Timestamp","Beneficiary_ID","Phone","Full_Name","State","LGA","Role","Primary_Crop","Channel","Message","Status","Gateway_ID","Cost_Kobo"])
    for log,p in q.order_by(SMSLog.sent_at.desc()).all():
        channel = "WhatsApp" if (log.status=="whatsapp" or (log.message or "").startswith("[WHATSAPP]")) else "SMS"
        w.writerow([log.sent_at.strftime("%Y-%m-%d %H:%M:%S"),p.beneficiary_id,p.phone,p.full_name,
            p.state,p.lga,p.role,p.primary_crop or "",channel,log.message,log.status,log.gateway_id or "",log.cost_kobo])
    filename = f"vcdp_sms_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(io.BytesIO(buf.getvalue().encode()),mimetype="text/csv",
                     as_attachment=True,download_name=filename)

# ── Templates & SMS Test ───────────────────────────────────────────────────
@api.route("/seed_templates", methods=["POST"])
@login_required
def seed_templates_route():
    from seeds.templates import seed_all_templates
    created = seed_all_templates(db, Template)
    return jsonify({"message":f"Created {created} new template(s)","total":Template.query.count()})

@api.route("/api/sms-test")
@login_required
def sms_test():
    result = test_connection()
    return jsonify(result)

@api.route("/api/whatsapp-test")
@login_required
def whatsapp_test():
    """
    Verify the WhatsApp dispatch channel is ready:
    1. wa.me (WhatsApp click-to-chat service) reachable from this server
    2. Count of WhatsApp dispatches already logged
    3. Beneficiaries with a dedicated WhatsApp contact on file
    """
    import requests as _rq
    scope = current_user.state if current_user.role in STATE_SCOPED else None
    try:
        r = _rq.head("https://wa.me", timeout=6, allow_redirects=True)
        reachable = r.status_code < 500
    except Exception:
        reachable = False
    wa_logs = SMSLog.query.filter(SMSLog.status == "whatsapp")
    if scope:
        wa_logs = wa_logs.join(Participant, SMSLog.participant_id == Participant.id)\
                         .filter(Participant.state == scope)
    pq = Participant.query.filter(Participant.whatsapp_contact.isnot(None))
    if scope: pq = pq.filter_by(state=scope)
    return jsonify({
        "status": "ok" if reachable else "unreachable",
        "wa_me_reachable": reachable,
        "whatsapp_dispatches_logged": wa_logs.count(),
        "beneficiaries_with_whatsapp_contact": pq.count(),
        "note": "Delivery uses WhatsApp click-to-chat (wa.me) links and Broadcast Lists — no API key required."
    })

# ── Weather Stations (Tuya FJ3395 / 7-in-1 devices) — Health Monitoring ────
def _station_scope_query():
    """Scope station visibility: owner/admin see all; SPMU/agents/champions see
    their own state; AWS Supplier sees only stations tagged with their supplier
    name (their equipment), regardless of state."""
    q = WeatherStation.query
    if current_user.role == "aws_supplier":
        return q.filter_by(supplier=current_user.supplier) if current_user.supplier else q.filter(False)
    if current_user.role in STATE_SCOPED:
        return q.filter_by(state=current_user.state)
    return q

def _station_json(s):
    return {
        "id": s.id, "state": s.state, "lga": s.lga,
        "device_id": s.device_id, "device_name": s.device_name, "supplier": s.supplier,
        "status": s.status, "is_online": s.is_online,
        "last_seen": s.last_seen.strftime("%Y-%m-%d %H:%M:%S") if s.last_seen else None,
        "battery_level": s.battery_level, "signal_strength": s.signal_strength,
        "sensor_status": s.sensor_status, "last_error": s.last_error,
    }

@api.route("/api/stations")
@login_required
def list_stations():
    """List weather stations, scoped by role (state, or AWS supplier)."""
    stations = _station_scope_query().order_by(WeatherStation.state, WeatherStation.lga).all()
    return jsonify({"stations": [_station_json(s) for s in stations],
                     "tuya_configured": bool(Config.TUYA_CLIENT_ID)})


@api.route("/api/stations/health")
@login_required
def stations_health_summary():
    """Aggregate health summary for the AWS Station Health dashboard card."""
    stations = _station_scope_query().all()
    online  = sum(1 for s in stations if s.is_online is True)
    offline = sum(1 for s in stations if s.is_online is not True)
    low_batt = sum(1 for s in stations if s.battery_level is not None and s.battery_level < 20)
    faults  = sum(1 for s in stations if s.sensor_status == "fault")
    by_state = {}
    for s in stations:
        d = by_state.setdefault(s.state, {"total":0,"online":0,"offline":0})
        d["total"] += 1
        d["online" if s.is_online else "offline"] += 1
    return jsonify({"total": len(stations), "online": online, "offline": offline,
                     "low_battery": low_batt, "sensor_faults": faults,
                     "by_state": [{"state":k, **v} for k,v in by_state.items()]})


@api.route("/api/stations/add", methods=["POST"])
@login_required
def add_station():
    """Register a new weather station for an LGA.
    Owner/NPMU/AWS Supplier can register for any state; SPMU only their own."""
    state = request.form.get("state","").strip()
    lga   = request.form.get("lga","").strip().title()
    device_id   = request.form.get("device_id","").strip()
    device_name = request.form.get("device_name","").strip()
    supplier    = request.form.get("supplier","").strip()

    if state not in Config.VALID_STATES:
        return jsonify({"error": f"Invalid state: {state}"}), 400
    if lga not in get_state_lgas(state):
        return jsonify({"error": f"LGA '{lga}' not valid for {state}"}), 400
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    if current_user.role in STATE_SCOPED and current_user.state != state:
        return jsonify({"error": "You can only add stations for your own state"}), 403

    existing = WeatherStation.query.filter_by(device_id=device_id).first()
    if existing:
        return jsonify({"error": f"Device ID already registered for {existing.lga}, {existing.state}"}), 400

    if not supplier:
        supplier = current_user.supplier if current_user.role == "aws_supplier" else "Green Allied Nigeria Limited"

    station = WeatherStation(state=state, lga=lga, device_id=device_id,
                              device_name=device_name or f"{lga} Station",
                              supplier=supplier, status="pending")
    db.session.add(station)
    db.session.commit()
    return jsonify({"message": f"Station registered for {lga}, {state}", "id": station.id})


@api.route("/api/stations/<int:station_id>/test", methods=["POST"])
@login_required
def test_station(station_id):
    """Full health check: online/offline, last data received, battery, signal, sensor status."""
    station = WeatherStation.query.get_or_404(station_id)
    if current_user.role == "aws_supplier":
        if station.supplier != current_user.supplier:
            return jsonify({"error": "Not authorized for this station"}), 403
    elif current_user.role in STATE_SCOPED and current_user.state != station.state:
        return jsonify({"error": "Not authorized for this station"}), 403

    health = tuya_client.get_device_health(station.device_id)
    reading = health.get("reading")

    station.is_online = health.get("online")
    station.last_error = health.get("error")
    if reading:
        station.last_seen = datetime.utcnow()
        station.battery_level = reading.get("battery_level")
        station.signal_strength = reading.get("signal_strength")
        station.sensor_status = reading.get("sensor_status")
        station.status = "active"
    elif health.get("online") is False or health.get("error"):
        station.status = "offline"
    db.session.commit()

    return jsonify({"ok": reading is not None, "status": station.status,
                     "is_online": station.is_online, "last_active": health.get("last_active"),
                     "reading": reading, "error": health.get("error"),
                     "station": _station_json(station)})


@api.route("/api/stations/<int:station_id>", methods=["DELETE"])
@login_required
def delete_station(station_id):
    station = WeatherStation.query.get_or_404(station_id)
    if current_user.role == "aws_supplier":
        if station.supplier != current_user.supplier:
            return jsonify({"error": "Not authorized for this station"}), 403
    elif current_user.role in STATE_SCOPED and current_user.state != station.state:
        return jsonify({"error": "Not authorized for this station"}), 403
    db.session.delete(station)
    db.session.commit()
    return jsonify({"message": "Station removed"})


@api.route("/api/tuya-test")
@login_required
def tuya_test():
    """Test Tuya Cloud credentials/connectivity."""
    return jsonify(tuya_client.test_connection())

# ── Beneficiary cleanup (delete by State / LGA) ────────────────────────────
@api.route("/api/beneficiaries/count", methods=["GET"])
@login_required
def count_beneficiaries():
    """Return how many beneficiary records match a State (and optional LGA) — used to
    preview a deletion before it happens."""
    state = (request.args.get("state") or "").strip()
    lga   = (request.args.get("lga") or "").strip().title()

    if not state:
        return jsonify({"error": "State is required"}), 400
    if state not in Config.VALID_STATES:
        return jsonify({"error": f"Invalid state: {state}"}), 400
    if current_user.role in STATE_SCOPED and current_user.state != state:
        return jsonify({"error": "You can only manage beneficiaries for your own state"}), 403
    if lga and lga not in get_state_lgas(state):
        return jsonify({"error": f"LGA '{lga}' not valid for {state}"}), 400

    q = Participant.query.filter_by(state=state)
    if lga:
        q = q.filter_by(lga=lga)
    count = q.count()
    sms_count = db.session.query(SMSLog).join(
        Participant, SMSLog.participant_id == Participant.id
    ).filter(Participant.state == state)
    if lga:
        sms_count = sms_count.filter(Participant.lga == lga)

    return jsonify({
        "state": state, "lga": lga or None,
        "beneficiary_count": count,
        "sms_log_count": sms_count.count(),
    })


@api.route("/api/beneficiaries/delete", methods=["POST"])
@login_required
def delete_beneficiaries():
    """
    Bulk-delete beneficiary records (and their SMS logs) for a State, or for a
    specific State+LGA. Requires confirm=yes to actually perform the deletion —
    without it, this just returns the count (same as /api/beneficiaries/count).
    """
    state   = (request.form.get("state") or "").strip()
    lga     = (request.form.get("lga") or "").strip().title()
    confirm = (request.form.get("confirm") or "").strip().lower()

    if not state:
        return jsonify({"error": "State is required"}), 400
    if state not in Config.VALID_STATES:
        return jsonify({"error": f"Invalid state: {state}"}), 400
    if current_user.role in STATE_SCOPED and current_user.state != state:
        return jsonify({"error": "You can only manage beneficiaries for your own state"}), 403
    if lga and lga not in get_state_lgas(state):
        return jsonify({"error": f"LGA '{lga}' not valid for {state}"}), 400

    q = Participant.query.filter_by(state=state)
    if lga:
        q = q.filter_by(lga=lga)

    participants = q.all()
    count = len(participants)

    if confirm != "yes":
        return jsonify({
            "confirmed": False,
            "state": state, "lga": lga or None,
            "beneficiary_count": count,
            "message": f"This will permanently delete {count} beneficiary record(s) "
                       f"{'in ' + lga + ', ' if lga else 'across all LGAs in '}{state}, "
                       f"including their SMS history. Send confirm=yes to proceed."
        })

    if count == 0:
        return jsonify({"deleted": 0, "sms_logs_deleted": 0,
                         "message": "No matching records found — nothing to delete."})

    ids = [p.id for p in participants]
    sms_deleted = SMSLog.query.filter(SMSLog.participant_id.in_(ids)).delete(synchronize_session=False)
    ben_deleted = q.delete(synchronize_session=False)
    db.session.commit()

    upsert_metric("total_participants", Participant.query.count())

    scope_desc = f"{lga}, {state}" if lga else f"all LGAs in {state}"
    return jsonify({
        "deleted": ben_deleted,
        "sms_logs_deleted": sms_deleted,
        "message": f"Deleted {ben_deleted} beneficiary record(s) and {sms_deleted} SMS log(s) for {scope_desc}."
    })

# ── Programme LGA management (Owner / NPMU only) ───────────────────────────
@api.route("/api/programme-lgas")
@login_required
def list_programme_lgas():
    """
    Full LGA list grouped by state, for the Manage LGAs screen.
    SPMU can view (read-only) their own state; only Owner/NPMU can add/remove.
    """
    data = get_all_state_lgas()
    if current_user.role in STATE_SCOPED:
        data = {current_user.state: data.get(current_user.state, [])}
    return jsonify({
        "lgas_by_state": data,
        "can_edit": current_user.role in ("owner","admin"),
        "states": Config.VALID_STATES,
    })


@api.route("/api/programme-lgas/add", methods=["POST"])
@login_required
def add_programme_lga():
    """Owner/NPMU only — add a new LGA to a state's programme list."""
    if current_user.role not in ("owner","admin"):
        return jsonify({"error": "Only the Programme Administrator or NPMU can add LGAs"}), 403

    state = (request.form.get("state") or "").strip()
    lga   = (request.form.get("lga") or "").strip().title()

    if state not in Config.VALID_STATES:
        return jsonify({"error": f"Invalid state: {state}"}), 400
    if not lga:
        return jsonify({"error": "LGA name is required"}), 400

    existing = ProgrammeLGA.query.filter_by(state=state, lga=lga).first()
    if existing:
        return jsonify({"error": f"'{lga}' is already a programme LGA for {state}"}), 400

    db.session.add(ProgrammeLGA(state=state, lga=lga, added_by=current_user.username))
    db.session.commit()
    return jsonify({"message": f"'{lga}' added to {state}", "lgas": get_state_lgas(state)})


@api.route("/api/programme-lgas/remove", methods=["POST"])
@login_required
def remove_programme_lga():
    """
    Owner/NPMU only — remove an LGA from a state's programme list.
    Refuses to remove an LGA that still has beneficiaries registered under it,
    to avoid silently orphaning real data — those must be reassigned or
    deleted first via Manage Beneficiary Data.
    """
    if current_user.role not in ("owner","admin"):
        return jsonify({"error": "Only the Programme Administrator or NPMU can remove LGAs"}), 403

    state = (request.form.get("state") or "").strip()
    lga   = (request.form.get("lga") or "").strip().title()
    force = (request.form.get("force") or "").strip().lower() == "yes"

    row = ProgrammeLGA.query.filter_by(state=state, lga=lga).first()
    if not row:
        return jsonify({"error": f"'{lga}' is not currently a programme LGA for {state}"}), 404

    ben_count = Participant.query.filter_by(state=state, lga=lga).count()
    if ben_count > 0 and not force:
        return jsonify({
            "error": f"{ben_count} beneficiary record(s) still exist under {lga}, {state}. "
                     f"Remove or reassign them first, or resend with force=yes to remove the LGA "
                     f"anyway (existing records keep their LGA value but it will no longer be selectable).",
            "beneficiary_count": ben_count,
        }), 400

    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": f"'{lga}' removed from {state}", "lgas": get_state_lgas(state)})

# ── Send Custom Message (Owner / NPMU only) ──────────────────────────────────
@api.route("/api/send-custom-message", methods=["POST"])
@login_required
def send_custom_message():
    """Owner/NPMU/SPMU — send a custom SMS message to beneficiaries in a state/LGA."""
    if current_user.role not in ("owner","admin","spmu"):
        return jsonify({"error": "Access denied"}), 403
    
    state = request.form.get("state","").strip()
    lga = request.form.get("lga","").strip()
    message = request.form.get("message","").strip()
    
    # SPMU can only send to their own state
    if current_user.role in STATE_SCOPED:
        if current_user.state and state != current_user.state:
            return jsonify({"error": f"You can only send messages in {current_user.state}"}), 403
        state = current_user.state
    
    if not state or state not in Config.VALID_STATES:
        return jsonify({"error": "Invalid state"}), 400
    if not message or len(message) < 5:
        return jsonify({"error": "Message must be at least 5 characters"}), 400
    if len(message) > 306:
        return jsonify({"error": "Message exceeds 306 characters (2 SMS pages)"}), 400
    
    q = Participant.query.filter_by(state=state, opted_in_sms=True)
    if lga:
        q = q.filter_by(lga=lga)
    
    participants = q.all()
    if not participants:
        return jsonify({"recipients": 0, "message": "No opted-in beneficiaries found in this area"})
    
    sms_gateway = SMSGateway()
    sent_count = 0
    failed_phones = []
    
    for p in participants:
        try:
            result = sms_gateway.send_sms(p.phone_primary, message)
            if result:
                log = SMSLog(
                    participant_id=p.id,
                    message=f"[CUSTOM] {message}",
                    sms_count=1,
                    cost_kobo=int(os.getenv("SMS_COST_KOBO", 600))
                )
                db.session.add(log)
                sent_count += 1
        except Exception as e:
            failed_phones.append(p.phone_primary)
    
    db.session.commit()
    return jsonify({
        "recipients": len(participants),
        "sent": sent_count,
        "failed": len(failed_phones),
        "failed_phones": failed_phones[:10],
        "message": f"Sent to {sent_count}/{len(participants)} beneficiaries"
    })

# ── Team Management: Extension Agents & Climate Champions ──────────────────
# Owner/NPMU manage any user; SPMU manage Extension Agents and Climate
# Champions ONLY within their own state, assigned to an LGA (and optional
# FO cluster) in that state.

TEAM_ROLES = ("extension_agent", "climate_champion")

@api.route("/api/users", methods=["GET"])
@login_required
def list_users():
    if current_user.role in ("owner", "admin"):
        q = User.query
    elif current_user.role == "spmu":
        q = User.query.filter(User.role.in_(TEAM_ROLES), User.state == current_user.state)
    else:
        return jsonify({"error": "Not authorized"}), 403
    users = q.order_by(User.role, User.state, User.username).all()
    return jsonify({"users": [{
        "id": u.id, "username": u.username, "email": u.email, "role": u.role,
        "state": u.state, "lga": u.lga, "cluster": u.cluster,
        "created": u.created_at.strftime("%Y-%m-%d") if u.created_at else None
    } for u in users]})

@api.route("/api/users/add", methods=["POST"])
@login_required
def add_user():
    if current_user.role not in ("owner", "admin", "spmu"):
        return jsonify({"error": "Not authorized"}), 403
    username = (request.form.get("username") or "").strip().lower()
    email    = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    role     = (request.form.get("role") or "").strip().lower()
    state    = (request.form.get("state") or "").strip()
    lga      = (request.form.get("lga") or "").strip()
    cluster  = (request.form.get("cluster") or "").strip()

    if not username or not email or not password:
        return jsonify({"error": "Username, email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    # SPMU restrictions: only team roles, only own state, LGA required
    if current_user.role == "spmu":
        if role not in TEAM_ROLES:
            return jsonify({"error": "SPMU can only add Extension Agents and Climate Champions"}), 403
        state = current_user.state  # force own state
        if not lga:
            return jsonify({"error": "LGA is required for Extension Agents and Climate Champions"}), 400
    else:
        if role not in TEAM_ROLES + ("spmu", "admin"):
            return jsonify({"error": "Invalid role"}), 400
        if role in TEAM_ROLES and (not state or not lga):
            return jsonify({"error": "State and LGA are required for this role"}), 400

    # Validate LGA belongs to the state (live ProgrammeLGA table)
    if lga:
        valid = ProgrammeLGA.query.filter_by(state=state, lga=lga).first()
        if not valid:
            return jsonify({"error": f"'{lga}' is not a programme LGA in {state}"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    u = User(username=username, email=email, role=role,
             state=state or None, lga=lga or None, cluster=cluster or None)
    u.set_password(password)
    db.session.add(u); db.session.commit()
    logger.info(f"User '{username}' ({role}, {state}/{lga}) created by {current_user.username}")
    return jsonify({"message": f"{role.replace('_',' ').title()} '{username}' created for {lga or state or 'all states'}",
                    "id": u.id})

@api.route("/api/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    u = User.query.get(user_id)
    if not u: return jsonify({"error": "User not found"}), 404
    if u.role == "owner":
        return jsonify({"error": "The owner account cannot be deleted"}), 403
    if u.id == current_user.id:
        return jsonify({"error": "You cannot delete your own account"}), 403
    if current_user.role == "spmu":
        if u.role not in TEAM_ROLES or u.state != current_user.state:
            return jsonify({"error": "You can only remove Agents/Champions in your own state"}), 403
    elif current_user.role not in ("owner", "admin"):
        return jsonify({"error": "Not authorized"}), 403
    name = u.username
    db.session.delete(u); db.session.commit()
    logger.info(f"User '{name}' deleted by {current_user.username}")
    return jsonify({"message": f"User '{name}' removed"})

# ── IFAD Recommendation: Field Reports & Adoption Tracking ──────────────────
FIELD_REPORT_ROLES = ("extension_agent", "climate_champion", "spmu")

@api.route("/api/field-reports/add", methods=["POST"])
@login_required
def add_field_report():
    """Extension Agent / Climate Champion (or SPMU on their behalf) submits a
    field report — including how many farmers actually followed the advice,
    per IFAD's adoption-tracking recommendation."""
    if current_user.role not in FIELD_REPORT_ROLES + ("owner", "admin"):
        return jsonify({"error": "Not authorized"}), 403

    state = current_user.state if current_user.role in STATE_SCOPED else request.form.get("state","").strip()
    lga   = current_user.lga if current_user.role in ("extension_agent","climate_champion") and current_user.lga else request.form.get("lga","").strip()
    if not state or not lga:
        return jsonify({"error": "State and LGA are required"}), 400

    def _int(name):
        try: return max(0, int(request.form.get(name, 0) or 0))
        except ValueError: return 0

    report_date = date.today()
    raw_date = request.form.get("report_date","").strip()
    if raw_date:
        try: report_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError: pass

    report = FieldReport(
        submitted_by_id=current_user.id, role_at_submission=current_user.role,
        state=state, lga=lga, cluster=request.form.get("cluster","").strip() or current_user.cluster,
        report_date=report_date,
        farmers_reached=_int("farmers_reached"),
        advisory_delivered=request.form.get("advisory_delivered","true").lower() != "false",
        farmers_adopted=_int("farmers_adopted"),
        farmers_partial=_int("farmers_partial"),
        farmers_not_adopted=_int("farmers_not_adopted"),
        activities_notes=request.form.get("activities_notes","").strip(),
        challenges_notes=request.form.get("challenges_notes","").strip(),
    )
    db.session.add(report); db.session.commit()
    return jsonify({"message": "Field report submitted", "id": report.id,
                     "adoption_rate_pct": report.adoption_rate_pct})


@api.route("/api/field-reports")
@login_required
def list_field_reports():
    """List field reports — scoped by role. Agents/Champions see only their
    own; SPMU sees their state; Owner/NPMU see everything."""
    q = FieldReport.query
    if current_user.role in ("extension_agent", "climate_champion"):
        q = q.filter_by(submitted_by_id=current_user.id)
    elif current_user.role == "spmu":
        q = q.filter_by(state=current_user.state)
    elif current_user.role not in ("owner", "admin"):
        return jsonify({"error": "Not authorized"}), 403
    reports = q.order_by(FieldReport.report_date.desc(), FieldReport.created_at.desc()).limit(200).all()
    return jsonify({"reports": [{
        "id": r.id, "submitted_by": r.submitted_by.username if r.submitted_by else "—",
        "role": r.role_at_submission, "state": r.state, "lga": r.lga, "cluster": r.cluster,
        "date": r.report_date.strftime("%Y-%m-%d") if r.report_date else None,
        "farmers_reached": r.farmers_reached, "advisory_delivered": r.advisory_delivered,
        "farmers_adopted": r.farmers_adopted, "farmers_partial": r.farmers_partial,
        "farmers_not_adopted": r.farmers_not_adopted, "adoption_rate_pct": r.adoption_rate_pct,
        "activities_notes": r.activities_notes, "challenges_notes": r.challenges_notes,
    } for r in reports]})


@api.route("/api/field-reports/summary")
@login_required
def field_reports_summary():
    """Aggregate adoption-tracking summary for Analytics / dashboard."""
    q = FieldReport.query
    if current_user.role in STATE_SCOPED:
        q = q.filter_by(state=current_user.state)
    reports = q.all()
    reached  = sum(r.farmers_reached or 0 for r in reports)
    adopted  = sum(r.farmers_adopted or 0 for r in reports)
    partial  = sum(r.farmers_partial or 0 for r in reports)
    notadopt = sum(r.farmers_not_adopted or 0 for r in reports)
    total_tracked = adopted + partial + notadopt
    rate = round((adopted + 0.5*partial) / total_tracked * 100, 1) if total_tracked else None
    return jsonify({"report_count": len(reports), "farmers_reached": reached,
                     "farmers_adopted": adopted, "farmers_partial": partial,
                     "farmers_not_adopted": notadopt, "overall_adoption_rate_pct": rate})


# ── IFAD Recommendation: Farmer Feedback ("Was this advisory useful?") ──────
@api.route("/api/feedback/add", methods=["POST"])
@login_required
def add_feedback_logged():
    """Extension Agent / Climate Champion logs feedback gathered in person
    during a field visit (most farmers won't use the public web portal)."""
    if current_user.role not in FIELD_REPORT_ROLES + ("owner", "admin"):
        return jsonify({"error": "Not authorized"}), 403
    state = current_user.state if current_user.role in STATE_SCOPED else request.form.get("state","").strip()
    if not state:
        return jsonify({"error": "State is required"}), 400
    fb = AdvisoryFeedback(
        state=state, lga=request.form.get("lga","").strip() or current_user.lga,
        channel="field_agent", farmer_name=request.form.get("farmer_name","").strip(),
        farmer_phone=request.form.get("farmer_phone","").strip(),
        useful=request.form.get("useful","true").lower() == "true",
        comment=request.form.get("comment","").strip(), logged_by_id=current_user.id)
    db.session.add(fb); db.session.commit()
    return jsonify({"message": "Feedback logged", "id": fb.id})


@api.route("/api/feedback")
@login_required
def list_feedback():
    """List farmer feedback — scoped by role."""
    q = AdvisoryFeedback.query
    if current_user.role in STATE_SCOPED:
        q = q.filter_by(state=current_user.state)
    elif current_user.role not in ("owner", "admin"):
        return jsonify({"error": "Not authorized"}), 403
    items = q.order_by(AdvisoryFeedback.created_at.desc()).limit(200).all()
    return jsonify({"feedback": [{
        "id": f.id, "state": f.state, "lga": f.lga, "channel": f.channel,
        "farmer_name": f.farmer_name, "farmer_phone": f.farmer_phone,
        "useful": f.useful, "comment": f.comment,
        "logged_by": f.logged_by.username if f.logged_by else "Self-submitted (portal)",
        "created": f.created_at.strftime("%Y-%m-%d %H:%M"),
    } for f in items]})


@api.route("/api/feedback/summary")
@login_required
def feedback_summary():
    q = AdvisoryFeedback.query
    if current_user.role in STATE_SCOPED:
        q = q.filter_by(state=current_user.state)
    total = q.count()
    useful = q.filter_by(useful=True).count()
    pct = round(useful/total*100, 1) if total else None
    return jsonify({"total": total, "useful": useful, "not_useful": total-useful, "useful_pct": pct})

# ── Public Weather Portal (no login required) ───────────────────────────────
# CIDU — AI-Powered Climate Information & Advisory Platform
# Public-facing, mobile-responsive. Daily weather + advisory + chatbot + feedback.

@api.route("/portal")
def public_portal():
    return render_template("portal.html")


@api.route("/api/portal/states")
def portal_states():
    return jsonify({"states": Config.VALID_STATES})


@api.route("/api/portal/lgas")
def portal_lgas():
    state = request.args.get("state","").strip()
    return jsonify({"lgas": get_state_lgas(state) if state else []})


@api.route("/api/portal/weather")
def portal_weather():
    """Today's weather + localized advisory for a State/LGA — public, read-only."""
    state = request.args.get("state","").strip()
    lga   = request.args.get("lga","").strip()
    lang  = request.args.get("lang","en").strip().lower()
    if state not in Config.VALID_STATES or lga not in get_state_lgas(state):
        return jsonify({"error": "Please select a valid State and LGA"}), 400
    weather = get_weather_for_lga(state, lga)
    if not weather:
        return jsonify({"error": "Weather data temporarily unavailable for this location"}), 503
    template = _get_template("", lang) or _get_template("", "en")
    advisory = _build_message(template, weather)[:306] if template else None
    return jsonify({
        "state": state, "lga": lga, "language": lang,
        "temperature_c": round(weather.max_temp_c or 0, 1),
        "rainfall_mm": round(weather.rainfall_mm or 0, 1),
        "alert": weather.alert or "No active alerts",
        "advisory": advisory, "advisory_characters": len(advisory) if advisory else 0,
        "source": weather.source, "updated": weather.fetched_at.strftime("%Y-%m-%d %H:%M") if weather.fetched_at else None,
    })


@api.route("/api/portal/feedback", methods=["POST"])
def portal_feedback():
    """Public 'Was this advisory useful?' feedback — no login required."""
    state = request.form.get("state","").strip()
    if state not in Config.VALID_STATES:
        return jsonify({"error": "Invalid state"}), 400
    fb = AdvisoryFeedback(
        state=state, lga=request.form.get("lga","").strip(), channel="portal",
        farmer_name=request.form.get("farmer_name","").strip(),
        farmer_phone=request.form.get("farmer_phone","").strip(),
        useful=request.form.get("useful","true").lower() == "true",
        comment=request.form.get("comment","").strip(), logged_by_id=None)
    db.session.add(fb); db.session.commit()
    return jsonify({"message": "Thank you for your feedback!"})


@api.route("/api/portal/chat", methods=["POST"])
def portal_chat():
    """
    Lightweight rule-based assistant for the public portal — answers common
    questions about today's weather/advisory using live station & NiMet-backed
    data, without requiring any external AI API key.
    """
    msg   = (request.form.get("message") or "").strip()
    state = (request.form.get("state") or "").strip()
    lga   = (request.form.get("lga") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a question — e.g. 'Will it rain today?' or 'What's the temperature in Bida?'"})

    low = msg.lower()

    # Try to detect a state/LGA mentioned in the message itself
    detected_state, detected_lga = state, lga
    for s in Config.VALID_STATES:
        if s.lower().replace(" state","") in low:
            detected_state = s
            break
    if detected_state:
        for l in get_state_lgas(detected_state):
            if l.lower() in low:
                detected_lga = l
                break
    else:
        # No state named — search every state's LGA list for a match
        # (e.g. "weather in Bida" without saying "Niger State")
        for s in Config.VALID_STATES:
            for l in get_state_lgas(s):
                if l.lower() in low:
                    detected_state, detected_lga = s, l
                    break
            if detected_state:
                break

    greetings = ("hi", "hello", "good morning", "good afternoon", "good evening", "hiya")
    if any(low.startswith(g) or low == g for g in greetings):
        return jsonify({"reply": "Hello! 👋 I'm the CIDU weather assistant. Ask me things like \"weather in Bida today\" or \"will it rain in Doma?\", or use the selectors above to see your local advisory."})

    if "feedback" in low or "useful" in low:
        return jsonify({"reply": "You can rate today's advisory using the 👍 Useful / 👎 Not Useful buttons above — your feedback helps improve future advisories."})

    if "help" in low or "what can you" in low:
        return jsonify({"reply": "I can share today's temperature, rainfall, and farming advisory for any VCDP state and LGA. Try: \"weather in Lafia\" or select your State/LGA above and tap 'Get Today's Advisory'."})

    if not detected_state or not detected_lga:
        return jsonify({"reply": "I couldn't identify a State/LGA in your message. Please select your State and LGA above, or ask like: \"weather in Bida, Niger State\"."})

    weather = get_weather_for_lga(detected_state, detected_lga)
    if not weather:
        return jsonify({"reply": f"Sorry, I don't have weather data for {detected_lga}, {detected_state} right now. Please try again shortly."})

    template = _get_template("", "en")
    advisory = _build_message(template, weather)[:306] if template else ""
    reply = (f"📍 {detected_lga}, {detected_state} — Today: {round(weather.max_temp_c or 0,1)}°C, "
             f"{round(weather.rainfall_mm or 0,1)}mm rain expected. {weather.alert or 'No active alerts.'}")
    if advisory:
        reply += f"\n\n🌾 Advisory: {advisory}"
    return jsonify({"reply": reply, "state": detected_state, "lga": detected_lga})
