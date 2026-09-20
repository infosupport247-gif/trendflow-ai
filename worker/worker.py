import os,json,time,redis,httpx
r=redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"),decode_responses=True)
API=os.getenv("API_URL","http://api:8000")
TOKEN=os.getenv("INTERNAL_SERVICE_TOKEN","")
while True:
    item=r.blpop("trendflow:jobs",timeout=5)
    if not item: continue
    _,raw=item
    try:
        job=json.loads(raw)
        typ=job.get("type")
        if typ=="autonomy_cycle":
            res=httpx.post(API+"/api/autonomy/execute/"+job["influencer_id"],headers={"X-Service-Token":TOKEN},timeout=600)
            res.raise_for_status()
        elif typ=="analytics":
            res=httpx.post(API+"/api/analytics/collect",headers={"X-Service-Token":TOKEN},json={"content_id":job["content_id"],"refresh":True},timeout=600)
            res.raise_for_status()
        else:
            r.rpush("trendflow:events",json.dumps({"status":"queued_for_provider_worker","job":job}))
    except Exception as exc:
        r.rpush("trendflow:dead-letter",raw)
        r.rpush("trendflow:events",json.dumps({"status":"failed","error":str(exc)}))
