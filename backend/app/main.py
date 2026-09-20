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
