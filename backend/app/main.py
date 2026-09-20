from __future__ import annotations
import os,json,uuid,secrets,urllib.parse
from datetime import datetime,timezone,timedelta
from typing import Any,Optional
from fastapi import FastAPI,HTTPException,UploadFile,File,Request,Depends,Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine,String,Text,DateTime,JSON,Boolean,Integer
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,sessionmaker
import redis,httpx
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from .services.ai import AIService,AIError
from .services.storage import Storage
from .services.vault import TokenVault
from .services.publishers import publisher_for,PublishError
from .services.analytics_collectors import collect,AnalyticsError
import jwt
from passlib.context import CryptContext

DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./trendflow.db'); REDIS_URL=os.getenv('REDIS_URL','redis://localhost:6379/0')
engine=create_engine(DATABASE_URL,connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
class Influencer(Base):
 __tablename__='influencers'; id:Mapped[str]=mapped_column(String(36),primary_key=True); name:Mapped[str]=mapped_column(String(120)); dna:Mapped[dict]=mapped_column(JSON,default=dict); status:Mapped[str]=mapped_column(String(40),default='active'); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Asset(Base):
 __tablename__='assets'; id:Mapped[str]=mapped_column(String(36),primary_key=True); influencer_id:Mapped[str]=mapped_column(String(36)); kind:Mapped[str]=mapped_column(String(40)); uri:Mapped[str]=mapped_column(Text); public_url:Mapped[str]=mapped_column(Text,default=''); metadata_json:Mapped[dict]=mapped_column('metadata',JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Content(Base):
 __tablename__='content'; id:Mapped[str]=mapped_column(String(36),primary_key=True); influencer_id:Mapped[str]=mapped_column(String(36)); title:Mapped[str]=mapped_column(String(200)); status:Mapped[str]=mapped_column(String(40),default='DRAFT'); payload:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class SocialAccount(Base):
 __tablename__='social_accounts'; id:Mapped[str]=mapped_column(String(36),primary_key=True); influencer_id:Mapped[str]=mapped_column(String(36)); platform:Mapped[str]=mapped_column(String(40)); handle:Mapped[str]=mapped_column(String(160),default=''); connected:Mapped[bool]=mapped_column(Boolean,default=False); external_id:Mapped[str]=mapped_column(String(200),default=''); token_ciphertext:Mapped[str]=mapped_column(Text,default=''); refresh_ciphertext:Mapped[str]=mapped_column(Text,default=''); expires_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); metadata_json:Mapped[dict]=mapped_column('metadata',JSON,default=dict)
class Analytics(Base):
 __tablename__='analytics'; id:Mapped[str]=mapped_column(String(36),primary_key=True); content_id:Mapped[str]=mapped_column(String(36)); platform:Mapped[str]=mapped_column(String(40)); metrics:Mapped[dict]=mapped_column(JSON,default=dict); captured_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class User(Base):
 __tablename__='users'; id:Mapped[str]=mapped_column(String(36),primary_key=True); email:Mapped[str]=mapped_column(String(255),unique=True); password_hash:Mapped[str]=mapped_column(String(255)); name:Mapped[str]=mapped_column(String(120),default=''); role:Mapped[str]=mapped_column(String(40),default='owner'); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Workspace(Base):
 __tablename__='workspaces'; id:Mapped[str]=mapped_column(String(36),primary_key=True); owner_id:Mapped[str]=mapped_column(String(36)); name:Mapped[str]=mapped_column(String(160)); plan:Mapped[str]=mapped_column(String(40),default='creator'); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class WorkspaceMember(Base):
 __tablename__='workspace_members'; id:Mapped[str]=mapped_column(String(36),primary_key=True); workspace_id:Mapped[str]=mapped_column(String(36)); user_id:Mapped[str]=mapped_column(String(36)); role:Mapped[str]=mapped_column(String(40),default='editor')
class CalendarItem(Base):
 __tablename__='calendar_items'; id:Mapped[str]=mapped_column(String(36),primary_key=True); influencer_id:Mapped[str]=mapped_column(String(36)); content_id:Mapped[str|None]=mapped_column(String(36),nullable=True); platform:Mapped[str]=mapped_column(String(40)); scheduled_at:Mapped[datetime]=mapped_column(DateTime); status:Mapped[str]=mapped_column(String(40),default='scheduled'); notes:Mapped[str]=mapped_column(Text,default='')
class BrandDeal(Base):
 __tablename__='brand_deals'; id:Mapped[str]=mapped_column(String(36),primary_key=True); influencer_id:Mapped[str]=mapped_column(String(36)); brand:Mapped[str]=mapped_column(String(180)); contact:Mapped[str]=mapped_column(String(255),default=''); stage:Mapped[str]=mapped_column(String(50),default='lead'); value:Mapped[int]=mapped_column(Integer,default=0); brief:Mapped[str]=mapped_column(Text,default=''); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
class Subscription(Base):
 __tablename__='subscriptions'; id:Mapped[str]=mapped_column(String(36),primary_key=True); user_id:Mapped[str]=mapped_column(String(36)); plan:Mapped[str]=mapped_column(String(40),default='starter'); status:Mapped[str]=mapped_column(String(40),default='active'); provider_customer_id:Mapped[str]=mapped_column(String(160),default=''); provider_subscription_id:Mapped[str]=mapped_column(String(160),default='')
class Audit(Base):
 __tablename__='audit'; id:Mapped[str]=mapped_column(String(36),primary_key=True); event:Mapped[str]=mapped_column(String(80)); entity_id:Mapped[str]=mapped_column(String(80)); details:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(timezone.utc))
rds=redis.from_url(REDIS_URL,decode_responses=True)
ai=AIService(); storage=Storage(); vault=TokenVault(); pwd=CryptContext(schemes=['bcrypt'],deprecated='auto'); JWT_SECRET=os.getenv('JWT_SECRET','').strip()
ENV=os.getenv('APP_ENV','development').lower(); INTERNAL_SERVICE_TOKEN=os.getenv('INTERNAL_SERVICE_TOKEN','').strip()
if ENV=='production' and (len(JWT_SECRET)<32 or JWT_SECRET=='change-me-in-production'): raise RuntimeError('JWT_SECRET must be a random value of at least 32 characters in production')
def audit(db,event,eid,details=None): db.add(Audit(id=str(uuid.uuid4()),event=event,entity_id=eid,details=details or {})); db.commit()
def enqueue(job): rds.rpush('trendflow:jobs',json.dumps(job))
def publicize(uri:str)->str:
 if not uri:return ''
 if uri.startswith(('http://','https://')):return uri
 base=os.getenv('S3_PUBLIC_BASE_URL','').rstrip('/')
 if uri.startswith('s3://') and base:
  bucket,key=uri[5:].split('/',1); return f'{base}/{key}'
 return ''
class InfluencerCreate(BaseModel): name:str; niche:str=''; location:str=''; audience:str=''; personality:dict={}; appearance:dict={}; voice:dict={}; brand:dict={}; rules:dict={}; platforms:list[str]=[]
class ContentCreate(BaseModel): influencer_id:str; title:str; payload:dict={}
class GenerateRequest(BaseModel): influencer_id:str; topic:str=''; format:str='reel'; goal:str='engagement'; include_image:bool=True; include_voice:bool=True
class MemoryRequest(BaseModel): influencer_id:str; category:str; value:Any
class ApprovalRequest(BaseModel): actor:str='human'
class ConnectRequest(BaseModel): influencer_id:str; platform:str; handle:str=''; redirect_uri:str='http://localhost:8000/api/social/callback'
class TokenExchange(BaseModel): account_id:str; code:str; redirect_uri:str
class PublishRequest(BaseModel): content_id:str; platform:str; asset_id:Optional[str]=None
class AnalyticsRequest(BaseModel): content_id:str; refresh:bool=True
class AuthRegister(BaseModel): email:str; password:str; name:str=''
class AuthLogin(BaseModel): email:str; password:str
class WorkspaceCreate(BaseModel): name:str; plan:str='creator'
class CalendarCreate(BaseModel): influencer_id:str; content_id:Optional[str]=None; platform:str; scheduled_at:datetime; notes:str=''
class BrandDealCreate(BaseModel): influencer_id:str; brand:str; contact:str=''; stage:str='lead'; value:int=0; brief:str=''
class SubscriptionCreate(BaseModel): plan:str
REQUESTS=Counter('trendflow_http_requests_total','HTTP requests',['method','path','status']); LATENCY=Histogram('trendflow_http_request_duration_seconds','HTTP request duration',['method','path'])
app=FastAPI(title='TrendFlow AI Influencer Operating System',version='6.1.0',docs_url='/docs' if ENV!='production' else None,redoc_url='/redoc' if ENV!='production' else None)
ALLOWED_ORIGINS=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:5173,http://localhost:8000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=ALLOWED_ORIGINS,allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type','X-Request-ID'])
@app.middleware('http')
async def metrics_middleware(request:Request,call_next):
 import time
 started=time.perf_counter(); response=await call_next(request); path=request.url.path
 REQUESTS.labels(request.method,path,str(response.status_code)).inc(); LATENCY.labels(request.method,path).observe(time.perf_counter()-started)
 response.headers['X-Request-ID']=request.headers.get('X-Request-ID',str(uuid.uuid4())); return response
async def auth_boundary(request:Request, call_next):
    path=request.url.path
    public = path.startswith('/health') or path in {'/api/auth/register','/api/auth/login','/api/social/callback'} or not path.startswith('/api/')
    if not public:
        auth=request.headers.get('Authorization','')
        if not auth.startswith('Bearer '):
            service=request.headers.get('X-Service-Token','')
            if not INTERNAL_SERVICE_TOKEN or service != INTERNAL_SERVICE_TOKEN:
                return __import__('fastapi').responses.JSONResponse({'detail':'Authentication required'},status_code=401)
    return await call_next(request)

@app.middleware('http')
async def security_middleware(request:Request, call_next):
    rid=request.headers.get('X-Request-ID') or str(uuid.uuid4())
    response=await call_next(request)
    response.headers['X-Request-ID']=rid
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if ENV == 'production': response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.get('/health/live')
def health_live(): return {'status':'ok'}

@app.get('/health/ready')
def health_ready():
    checks={}
    try:
        db=SessionLocal(); db.execute(__import__('sqlalchemy').text('SELECT 1')); checks['database']='ok'
    except Exception as e: checks['database']=f'error:{type(e).__name__}'
    try: rds.ping(); checks['redis']='ok'
    except Exception as e: checks['redis']=f'error:{type(e).__name__}'
    ok=all(v=='ok' for v in checks.values())
    return {'status':'ready' if ok else 'not_ready','checks':checks}

def issue_token(user):
 return jwt.encode({'sub':user.id,'email':user.email,'role':user.role,'exp':datetime.now(timezone.utc)+timedelta(days=7)},JWT_SECRET,algorithm='HS256')
def current_user(authorization:Optional[str]=Header(None)):
 if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
 try: return jwt.decode(authorization[7:],JWT_SECRET,algorithms=['HS256'])
 except Exception: raise HTTPException(401,'Invalid or expired token')

@app.post('/api/auth/register')
def register(x:AuthRegister):
 if len(x.password) < 12: raise HTTPException(400,'Password must be at least 12 characters')
 db=SessionLocal()
 if db.query(User).filter_by(email=x.email.lower()).first(): raise HTTPException(409,'Email already registered')
 u=User(id=str(uuid.uuid4()),email=x.email.lower(),password_hash=pwd.hash(x.password),name=x.name); db.add(u); db.flush()
 w=Workspace(id=str(uuid.uuid4()),owner_id=u.id,name=f"{x.name or x.email.split('@')[0]}'s Workspace",plan='creator'); db.add(w); db.add(WorkspaceMember(id=str(uuid.uuid4()),workspace_id=w.id,user_id=u.id,role='owner')); db.add(Subscription(id=str(uuid.uuid4()),user_id=u.id,plan='creator')); db.commit()
 return {'access_token':issue_token(u),'user':{'id':u.id,'email':u.email,'name':u.name},'workspace':{'id':w.id,'name':w.name,'plan':w.plan}}
@app.post('/api/auth/login')
def login(x:AuthLogin):
 db=SessionLocal(); u=db.query(User).filter_by(email=x.email.lower()).first()
 if not u or not pwd.verify(x.password,u.password_hash): raise HTTPException(401,'Invalid credentials')
 return {'access_token':issue_token(u),'user':{'id':u.id,'email':u.email,'name':u.name,'role':u.role}}
@app.get('/api/auth/me')
def me(claims=Depends(current_user)):
 db=SessionLocal(); u=db.get(User,claims['sub']); return {'id':u.id,'email':u.email,'name':u.name,'role':u.role}
@app.get('/api/workspaces')
def workspaces(claims=Depends(current_user)):
 db=SessionLocal(); return [{'id':w.id,'name':w.name,'plan':w.plan,'role':db.query(WorkspaceMember).filter_by(workspace_id=w.id,user_id=claims['sub']).first().role} for w in db.query(Workspace).join(WorkspaceMember,Workspace.id==WorkspaceMember.workspace_id).filter(WorkspaceMember.user_id==claims['sub']).all()]
@app.post('/api/workspaces')
def create_workspace(x:WorkspaceCreate,claims=Depends(current_user)):
 db=SessionLocal(); w=Workspace(id=str(uuid.uuid4()),owner_id=claims['sub'],name=x.name,plan=x.plan); db.add(w); db.add(WorkspaceMember(id=str(uuid.uuid4()),workspace_id=w.id,user_id=claims['sub'],role='owner')); db.commit(); return {'id':w.id,'name':w.name,'plan':w.plan}
@app.get('/api/calendar/{iid}')
def calendar(iid):
 db=SessionLocal(); return [{'id':x.id,'content_id':x.content_id,'platform':x.platform,'scheduled_at':x.scheduled_at,'status':x.status,'notes':x.notes} for x in db.query(CalendarItem).filter_by(influencer_id=iid).order_by(CalendarItem.scheduled_at).all()]
@app.post('/api/calendar')
def add_calendar(x:CalendarCreate):
 db=SessionLocal(); item=CalendarItem(id=str(uuid.uuid4()),**x.model_dump()); db.add(item); db.commit(); audit(db,'calendar_scheduled',item.id,x.model_dump()); return {'id':item.id,'status':item.status}
@app.delete('/api/calendar/{cid}')
def delete_calendar(cid):
 db=SessionLocal(); x=db.get(CalendarItem,cid)
 if not x: raise HTTPException(404,'Calendar item not found')
 db.delete(x); db.commit(); return {'deleted':True}
@app.get('/api/brand-deals/{iid}')
def brand_deals(iid):
 db=SessionLocal(); return [{'id':x.id,'brand':x.brand,'contact':x.contact,'stage':x.stage,'value':x.value,'brief':x.brief} for x in db.query(BrandDeal).filter_by(influencer_id=iid).order_by(BrandDeal.created_at.desc()).all()]
@app.post('/api/brand-deals')
def add_brand_deal(x:BrandDealCreate):
 db=SessionLocal(); d=BrandDeal(id=str(uuid.uuid4()),**x.model_dump()); db.add(d); db.commit(); audit(db,'brand_deal_created',d.id,x.model_dump()); return {'id':d.id,'stage':d.stage}
@app.patch('/api/brand-deals/{did}')
def update_brand_deal(did,patch:dict):
 db=SessionLocal(); d=db.get(BrandDeal,did)
 if not d: raise HTTPException(404,'Brand deal not found')
 for k in ('brand','contact','stage','value','brief'):
  if k in patch: setattr(d,k,patch[k])
 db.commit(); return {'id':d.id,'stage':d.stage,'value':d.value}
@app.get('/api/subscription')
def subscription(claims=Depends(current_user)):
 db=SessionLocal(); s=db.query(Subscription).filter_by(user_id=claims['sub']).first(); return {'plan':s.plan,'status':s.status,'stripe_configured':bool(os.getenv('STRIPE_SECRET_KEY'))}
@app.post('/api/subscription/checkout')
def checkout(x:SubscriptionCreate,claims=Depends(current_user)):
 if not os.getenv('STRIPE_SECRET_KEY'): return {'mode':'configuration_required','plan':x.plan,'message':'Set STRIPE_SECRET_KEY and PRICE_* variables to enable live checkout.'}
 return {'mode':'stripe_adapter_ready','plan':x.plan,'message':'Stripe checkout adapter boundary is ready; configure price IDs and webhook endpoint.'}
@app.get('/api/media-kit/{iid}')
def media_kit(iid):
 db=SessionLocal(); inf=db.get(Influencer,iid)
 if not inf: raise HTTPException(404,'Influencer not found')
 analytics=db.query(Analytics).join(Content,Analytics.content_id==Content.id).filter(Content.influencer_id==iid).all(); totals={}
 for a in analytics:
  for k,v in (a.metrics or {}).items():
   if isinstance(v,(int,float)): totals[k]=totals.get(k,0)+v
 return {'influencer':{'id':iid,'name':inf.name,'dna':inf.dna},'audience':inf.dna.get('audience',{}),'performance':totals,'deliverables':['Instagram Post','Instagram Reel','TikTok Video','YouTube Short','YouTube Video','UGC Package'],'rate_card':inf.dna.get('brand',{}).get('rate_card',{})}

OAUTH={
 'instagram':('META_APP_ID','META_APP_SECRET','https://www.instagram.com/oauth/authorize','instagram_business_basic,instagram_business_content_publish,instagram_business_manage_comments,instagram_business_manage_messages','https://graph.instagram.com/oauth/access_token'),
 'facebook':('META_APP_ID','META_APP_SECRET','https://www.facebook.com/v24.0/dialog/oauth','pages_show_list,pages_read_engagement,pages_manage_posts','https://graph.facebook.com/v24.0/oauth/access_token'),
 'threads':('META_APP_ID','META_APP_SECRET','https://www.threads.net/oauth/authorize','threads_basic,threads_content_publish,threads_read_replies,threads_manage_replies,threads_manage_insights','https://graph.threads.net/oauth/access_token'),
 'youtube':('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','https://accounts.google.com/o/oauth2/v2/auth','https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly','https://oauth2.googleapis.com/token'),
 'tiktok':('TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','https://www.tiktok.com/v2/auth/authorize/','user.info.basic,video.publish','https://open.tiktokapis.com/v2/oauth/token/'),
 'linkedin':('LINKEDIN_CLIENT_ID','LINKEDIN_CLIENT_SECRET','https://www.linkedin.com/oauth/v2/authorization','openid profile w_member_social','https://www.linkedin.com/oauth/v2/accessToken'),
 'x':('X_CLIENT_ID','X_CLIENT_SECRET','https://twitter.com/i/oauth2/authorize','tweet.read tweet.write users.read offline.access','https://api.x.com/2/oauth2/token'),
 'pinterest':('PINTEREST_APP_ID','PINTEREST_APP_SECRET','https://www.pinterest.com/oauth/','boards:read,boards:write,pins:read,pins:write','https://api.pinterest.com/v5/oauth/token')}
@app.get('/metrics')
def metrics(): return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.get('/health')
def health(): return {'ok':True,'version':'6.1.0','openai_configured':bool(ai.key),'vault_configured':bool(vault.fernet),'ffmpeg_worker':True}
@app.get('/api/capabilities')
def capabilities(): return {'working_services':['Influencer DNA','persistent memory','OpenAI text/image/voice/transcription','S3/MinIO assets','FFmpeg media rendering','OAuth token exchange + encrypted token vault','social publishing adapters','platform analytics collectors','autonomous queue','approval + authorization gates','audit trail'],'requires_credentials':['OPENAI_API_KEY','TOKEN_VAULT_KEY','social OAuth app credentials','public S3 URL for URL-based platforms','provider credentials for non-OpenAI video generation']}
@app.post('/api/influencers')
def create_influencer(x:InfluencerCreate):
 db=SessionLocal(); iid=str(uuid.uuid4()); dna={'identity':{'name':x.name,'location':x.location},'personality':x.personality,'brand':{'niche':x.niche,**x.brand},'audience':{'description':x.audience},'appearance':x.appearance,'voice':x.voice,'rules':x.rules,'memory':{'facts':[],'past_content':[],'audience_preferences':[]},'strategy':{'content_pillars':[],'cadence':{},'platforms':x.platforms}}
 if ai.client:
  try:
   p=ai.json(f'Build a complete creator operating profile for {x.name}. Niche {x.niche}. Audience {x.audience}. Location {x.location}. Return JSON with content_pillars,tone,recurring_series,posting_cadence,visual_rules,do_not_do,audience_hooks,platform_strategy.')
   dna['strategy'].update({k:p[k] for k in ('content_pillars','tone','recurring_series','posting_cadence','platform_strategy') if k in p}); dna['brand']['visual_rules']=p.get('visual_rules',[]); dna['rules']['do_not_do']=p.get('do_not_do',[]); dna['audience']['hooks']=p.get('audience_hooks',[])
  except Exception: pass
 db.add(Influencer(id=iid,name=x.name,dna=dna)); db.commit(); audit(db,'influencer_created',iid); return {'id':iid,'dna':dna}
@app.get('/api/influencers')
def list_influencers():
 db=SessionLocal(); return [{'id':x.id,'name':x.name,'status':x.status} for x in db.query(Influencer).all()]
@app.get('/api/influencers/{iid}')
def get_influencer(iid):
 db=SessionLocal(); x=db.get(Influencer,iid)
 if not x: raise HTTPException(404,'Influencer not found')
 return {'id':x.id,'name':x.name,'dna':x.dna,'status':x.status}
@app.patch('/api/influencers/{iid}/dna')
def update_dna(iid,patch:dict):
 db=SessionLocal(); x=db.get(Influencer,iid)
 if not x: raise HTTPException(404,'Influencer not found')
 x.dna={**x.dna,**patch}; db.commit(); audit(db,'dna_updated',iid,patch); return x.dna
@app.post('/api/memory')
def add_memory(x:MemoryRequest):
 db=SessionLocal(); inf=db.get(Influencer,x.influencer_id)
 if not inf: raise HTTPException(404,'Influencer not found')
 m=inf.dna.setdefault('memory',{}); m.setdefault(x.category,[]); m[x.category].append(x.value); db.commit(); audit(db,'memory_added',inf.id,{'category':x.category}); return m
