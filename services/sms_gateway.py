import requests, logging
from config import Config
logger = logging.getLogger(__name__)

def send_sms(phone, message):
    if not Config.SMS_API_KEY:
        return {"status":"simulated","gateway_id":f"SIM-{phone[-4:]}","cost_kobo":0}
    try:
        r = requests.post(Config.SMS_API_URL, json={
            "api_key":Config.SMS_API_KEY,"to":phone,"from":Config.SMS_SENDER_ID,
            "sms":message,"type":"plain","channel":"generic"
        }, timeout=20, headers={"Content-Type":"application/json"})
        d = r.json()
        code = str(d.get("code","")).lower()
        status = str(d.get("message_status",d.get("status",""))).lower()
        if code=="ok" or status in ("success","sent","delivered","ok"):
            return {"status":"success","gateway_id":str(d.get("message_id",d.get("messageId","OK"))),"cost_kobo":Config.SMS_COST_KOBO}
        return {"status":"failed","gateway_id":None,"cost_kobo":0,"error":d.get("message",str(d))}
    except requests.exceptions.ConnectionError as e:
        return {"status":"failed","gateway_id":None,"cost_kobo":0,"error":f"Cannot reach Termii: {e}"}
    except Exception as e:
        return {"status":"failed","gateway_id":None,"cost_kobo":0,"error":str(e)}

def check_balance():
    if not Config.SMS_API_KEY:
        return {"balance":0,"currency":"NGN","note":"No API key"}
    try:
        r = requests.get("https://api.ng.termii.com/api/wallet/balance",
                         params={"api_key":Config.SMS_API_KEY}, timeout=10)
        d = r.json()
        return {"balance":d.get("balance",0),"currency":d.get("currency","NGN")}
    except Exception as e:
        return {"balance":0,"currency":"NGN","error":str(e)}

def test_connection():
    if not Config.SMS_API_KEY:
        return {"ok":False,"balance":0,"message":"No API key configured. Set TERMII_API_KEY in .env"}
    result = check_balance()
    if "error" in result:
        return {"ok":False,"balance":0,"message":f"Connection failed: {result['error']}"}
    bal = result.get("balance",0)
    return {"ok":True,"balance":bal,"currency":result.get("currency","NGN"),
            "message":f"Connected successfully — Wallet Balance: NGN {bal:,}"}
