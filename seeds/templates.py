TEMPLATES = [
    ("en","Rice",     "VCDP CIDU: {alert} Rice farmers: plan field activities accordingly."),
    ("en","Cassava",  "VCDP CIDU: {alert} Adjust cassava planting/harvest plans accordingly."),
    ("en","Producer", "VCDP CIDU: {alert} Producers: protect your farm inputs."),
    ("en","Processor","VCDP CIDU: {alert} Processors: secure drying/storage areas."),
    ("en","Marketer", "VCDP CIDU: {alert} Marketers: plan transport & storage."),
    ("en","general",  "VCDP Weather: {alert} Plan farm activities carefully."),
    ("ha","Rice",     "VCDP CIDU: {alert} Manoman shinkafa: shirya ayyukan gona daidai."),
    ("ha","general",  "VCDP Yanayi: {alert} Yi shirin ayyukan gonar ka daidai."),
    ("ig","Rice",     "VCDP CIDU: {alert} Ndi oru osikapa: hazie oru ugbo ka o doziri."),
    ("ig","general",  "VCDP Ihu igwe: {alert} Hazie oru ugbo gi nke oma."),
    ("yo","Rice",     "VCDP CIDU: {alert} Awon agbe iresi: gbero ishe oko ni ona to ye."),
    ("yo","general",  "VCDP Ojo Ojo: {alert} She eto ishe oko re daadaa."),
    ("pcm","Rice",    "VCDP CIDU: {alert} Rice farmers, plan your farm work well-well."),
    ("pcm","Producer","VCDP CIDU: {alert} Producers, cover your farm inputs."),
    ("pcm","Processor","VCDP CIDU: {alert} Processors, secure your drying and storage areas."),
    ("pcm","Marketer","VCDP CIDU: {alert} Marketers, plan your transport and storage."),
    ("pcm","general", "VCDP Weather: {alert} Plan your farm work carefully."),
    # ── Nupe (nup) ── PLACEHOLDER TEXT: replace with verified Nupe translations
    # from your state linguist/Extension team. Structure & 306-char limit ready.
    ("nup","Rice",    "VCDP CIDU: {alert} Rice farmers: plan your farm work carefully. (Nupe translation pending)"),
    ("nup","Cassava", "VCDP CIDU: {alert} Adjust cassava planting/harvest plans. (Nupe translation pending)"),
    ("nup","Producer","VCDP CIDU: {alert} Producers: protect your farm inputs. (Nupe translation pending)"),
    ("nup","Processor","VCDP CIDU: {alert} Processors: secure drying/storage areas. (Nupe translation pending)"),
    ("nup","Marketer","VCDP CIDU: {alert} Marketers: plan transport & storage. (Nupe translation pending)"),
    ("nup","general", "VCDP Weather: {alert} Plan farm activities carefully. (Nupe translation pending)"),
]

def seed_all_templates(db, Template):
    """
    Seed templates. If a template with this (language, crop) already exists
    but still contains an old format (with {rain}/{temp} placeholders or the
    removed opt-out wording), update it in place so existing installs get the
    cleaned-up text too.
    """
    created = 0
    updated = 0
    new_by_key = {(lang, crop): content for lang, crop, content in TEMPLATES}
    OLD_MARKERS = ("STOP", "comot", "puo", "kuro", "fita", "{rain}", "{temp}")

    for (lang, crop), content in new_by_key.items():
        existing = Template.query.filter_by(language=lang, crop=crop).first()
        if not existing:
            db.session.add(Template(language=lang, crop=crop, content=content))
            created += 1
        elif any(m in existing.content for m in OLD_MARKERS):
            existing.content = content
            updated += 1

    db.session.commit()
    return created + updated
