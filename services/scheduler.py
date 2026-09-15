import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

logger = logging.getLogger(__name__)
WAT = timezone("Africa/Lagos")

def _auto_dispatch(app):
    with app.app_context():
        from models import db, Participant, SMSLog, Template
        from services.weather_api import get_weather_for_lga
        from services.sms_gateway import send_sms
        from config import Config
        logger.info("Scheduled broadcast started")
        pairs = db.session.query(Participant.state, Participant.lga).filter_by(cis_onboarded=True).distinct().all()
        total_sent = total_failed = 0
        for state, lga in pairs:
            weather = get_weather_for_lga(state, lga)
            if not weather: continue
            for role in Config.VALID_CATEGORIES:
                t = Template.query.filter_by(language="en", crop=role).first() or \
                    Template.query.filter_by(language="en", crop="general").first()
                if not t: continue
                msg = t.content.format(rain=round(weather.rainfall_mm or 0,1),
                    temp=round(weather.max_temp_c or 0,1), alert=weather.alert or "No alerts")
                for p in Participant.query.filter_by(state=state, lga=lga, cis_onboarded=True, role=role).all():
                    res = send_sms(p.phone, msg)
                    db.session.add(SMSLog(participant_id=p.id, message=msg, status=res["status"],
                        gateway_id=res.get("gateway_id"), cost_kobo=res.get("cost_kobo",0)))
                    if res["status"] in ("success","simulated"): total_sent += 1
                    else: total_failed += 1
        db.session.commit()
        logger.info(f"Broadcast done — sent:{total_sent} failed:{total_failed}")

def init_scheduler(app):
    scheduler = BackgroundScheduler(timezone=WAT)
    scheduler.add_job(lambda: _auto_dispatch(app),
        CronTrigger(day_of_week="mon,thu", hour=7, minute=0, timezone=WAT),
        id="weekly_sms", replace_existing=True, misfire_grace_time=3600)
    scheduler.start()
    logger.info("Scheduler started — Mon/Thu 07:00 WAT")
    return scheduler
