"""
Seeds the initial set of programme LGAs into the database (one-time, only
fires if the table is empty). After this, LGAs are managed entirely through
the database via the Owner/NPMU "Manage LGAs" screen — config.py is no
longer the source of truth for which LGAs are valid.
"""

INITIAL_LGAS = {
    "Anambra State":  ["Aguata","Anaocha","Awka North","Awka South","Ayamelum",
                        "Dunukofia","Idemili North","Idemili South","Ihiala","Njikoka",
                        "Nnewi North","Nnewi South","Ogbaru","Onitsha North","Onitsha South",
                        "Orumba North","Orumba South","Oyi"],
    "Benue State":    ["Gwer East","Logo","Vandeikya"],
    "Ebonyi State":   ["Abakaliki","Afikpo South","Ikwo"],
    "Enugu State":    ["Enugu","Udenu"],
    "Kogi State":     ["Ajaokuta","Kabba/Bunu","Olamaboro"],
    "Nasarawa State": ["Doma","Lafia"],
    "Niger State":    ["Bida","Edati","Kontagora","Mokwa"],
    "Ogun State":     ["Abeokuta North","Abeokuta South","Ado-Odo/Ota","Egbado North",
                        "Egbado South","Ewekoro","Ifo","Ijebu East","Ijebu North","Ijebu Ode",
                        "Obafemi Owode","Odeda","Sagamu"],
    "Taraba State":   ["Karim Lamido","Wukari"],
}


def seed_programme_lgas(db, ProgrammeLGA):
    if ProgrammeLGA.query.first():
        return 0  # already seeded — DB is now the source of truth, don't overwrite
    created = 0
    for state, lgas in INITIAL_LGAS.items():
        for lga in lgas:
            db.session.add(ProgrammeLGA(state=state, lga=lga, added_by="system_seed"))
            created += 1
    db.session.commit()
    return created
