OWNER_ADMIN = {"username":"yusufyau","email":"yusuf@noblen.org","password":"VCDP@Owner2026!","role":"owner","state":None}
NPMU_ADMIN = {"username":"npmu_admin","email":"admin@vcdp.gov.ng","password":"VCDP@Npmu2026!","role":"admin","state":None}
STATE_ADMINS = [
    {"username":"spmu_anambra", "email":"anambra@vcdp.gov.ng", "password":"VCDP@Anambra2026!", "role":"spmu","state":"Anambra State"},
    {"username":"spmu_benue",   "email":"benue@vcdp.gov.ng",   "password":"VCDP@Benue2026!",   "role":"spmu","state":"Benue State"},
    {"username":"spmu_ebonyi",  "email":"ebonyi@vcdp.gov.ng",  "password":"VCDP@Ebonyi2026!",  "role":"spmu","state":"Ebonyi State"},
    {"username":"spmu_enugu",   "email":"enugu@vcdp.gov.ng",   "password":"VCDP@Enugu2026!",   "role":"spmu","state":"Enugu State"},
    {"username":"spmu_kogi",    "email":"kogi@vcdp.gov.ng",    "password":"VCDP@Kogi2026!",    "role":"spmu","state":"Kogi State"},
    {"username":"spmu_nasarawa","email":"nasarawa@vcdp.gov.ng","password":"VCDP@Nasarawa2026!","role":"spmu","state":"Nasarawa State"},
    {"username":"spmu_niger",   "email":"niger@vcdp.gov.ng",   "password":"VCDP@Niger2026!",   "role":"spmu","state":"Niger State"},
    {"username":"spmu_ogun",    "email":"ogun@vcdp.gov.ng",    "password":"VCDP@Ogun2026!",    "role":"spmu","state":"Ogun State"},
    {"username":"spmu_taraba",  "email":"taraba@vcdp.gov.ng",  "password":"VCDP@Taraba2026!",  "role":"spmu","state":"Taraba State"},
]
ALL_ACCOUNTS = [OWNER_ADMIN, NPMU_ADMIN] + STATE_ADMINS

# AWS Supplier account — Green Allied Nigeria Limited monitors the automatic
# weather stations they supply across every VCDP state (cross-state access,
# scoped by 'supplier' rather than by 'state').
AWS_SUPPLIER_ADMIN = {"username":"greenallied_aws","email":"aws@greenalliedng.com",
    "password":"VCDP@GreenAllied2026!","role":"aws_supplier","state":None,
    "supplier":"Green Allied Nigeria Limited"}

def seed_admins(db, User):
    created = 0
    for acc in ALL_ACCOUNTS:
        if not User.query.filter_by(username=acc["username"]).first():
            u = User(username=acc["username"],email=acc["email"],role=acc["role"],state=acc.get("state"))
            u.set_password(acc["password"])
            db.session.add(u); created += 1
    if not User.query.filter_by(username=AWS_SUPPLIER_ADMIN["username"]).first():
        u = User(username=AWS_SUPPLIER_ADMIN["username"], email=AWS_SUPPLIER_ADMIN["email"],
                  role=AWS_SUPPLIER_ADMIN["role"], state=None, supplier=AWS_SUPPLIER_ADMIN["supplier"])
        u.set_password(AWS_SUPPLIER_ADMIN["password"])
        db.session.add(u); created += 1
    db.session.commit()
    return created
