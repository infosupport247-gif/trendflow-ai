import os,time,httpx
API=os.getenv("API_URL","http://api:8000"); SERVICE_TOKEN=os.getenv("INTERNAL_SERVICE_TOKEN",""); interval=int(os.getenv("AUTONOMY_INTERVAL_SECONDS","3600"))
while True:
    try:httpx.post(API+"/api/autonomy/dispatch",headers={"X-Service-Token":SERVICE_TOKEN},timeout=60)
    except Exception:pass
    time.sleep(interval)