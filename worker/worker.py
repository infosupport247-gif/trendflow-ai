import os,json,redis,httpx,time
r=redis.from_url(os.getenv("REDIS_URL","redis://redis:6379/0"),decode_responses=True)
API=os.getenv("API_URL","http://api:8000")
TOKEN=os.getenv("INTERNAL_SERVICE_TOKEN","")
def h(): return {"X-Service-Token":TOKEN} if TOKEN else {}
def get(path): return httpx.get(API+path,headers=h(),timeout=120)
def post(path,**kw): kw.setdefault("headers",h()); return httpx.post(API+path,timeout=600,**kw)
def process(job):
    typ=job.get("type")
    if typ=="autonomy_cycle":
        r=post("/api/autonomy/execute/"+job["influencer_id"]); r.raise_for_status(); return r.json()
    if typ=="production":
        items=get("/api/content"); items.raise_for_status()
        item=next((x for x in items.json() if x["id"]==job["content_id"]),None)
        if not item: raise RuntimeError("content not found")
        p=item.get("payload") or {}; iid=item["influencer_id"]
        if p.get("visual_prompt"):
            x=post("/api/assets/generate-image",params={"influencer_id":iid,"prompt":p["visual_prompt"],"size":"1024x1024"}); x.raise_for_status()
            d=x.json(); p["image_uri"]=d["uri"]; p["asset_id"]=d["id"]
        if p.get("voiceover"):
            x=post("/api/assets/generate-voice",params={"influencer_id":iid,"text":p["voiceover"],"voice":"alloy"}); x.raise_for_status()
            p["voice_uri"]=x.json()["uri"]
        x=post("/api/content/"+job["content_id"]+"/payload",json=p); x.raise_for_status()
        x=post("/api/content/"+job["content_id"]+"/qa"); x.raise_for_status(); return x.json()
    if typ=="analytics":
        x=post("/api/analytics/collect",json={"content_id":job["content_id"],"refresh":True}); x.raise_for_status(); return x.json()
    if typ=="publish":
        item=next((x for x in get("/api/content").json() if x["id"]==job["content_id"]),None)
        if not item: raise RuntimeError("content not found")
        out={}
        for platform in (item.get("payload") or {}).get("publish_to",[]): 
            x=post("/api/publish",json={"content_id":item["id"],"platform":platform,"asset_id":(item.get("payload") or {}).get("asset_id")}); x.raise_for_status(); out[platform]=x.json()
        return out
    raise RuntimeError("unknown job type")
while True:
    item=r.blpop("trendflow:jobs",timeout=5)
    if not item: continue
    _,raw=item
    try:
        job=json.loads(raw); result=process(job); r.rpush("trendflow:events",json.dumps({"status":"completed","job":job,"result":result},default=str))
    except Exception as exc:
        r.rpush("trendflow:dead-letter",raw); r.rpush("trendflow:events",json.dumps({"status":"failed","error":str(exc),"job":json.loads(raw)},default=str))
