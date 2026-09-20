from __future__ import annotations
import os,json,httpx
class PublishError(RuntimeError): pass
class Publisher:
 def __init__(self,account,token,metadata): self.account=account; self.token=token; self.meta=metadata or {}; self.timeout=180
 def headers(self): return {'Authorization':f'Bearer {self.token}'}
 def publish(self,payload,asset=None): raise NotImplementedError
class InstagramPublisher(Publisher):
 def publish(self,payload,asset=None):
  ig_id=self.meta.get('external_id') or self.meta.get('ig_user_id'); api=os.getenv('META_GRAPH_URL','https://graph.facebook.com/v24.0')
  if not ig_id or not asset or not asset.get('public_url'): raise PublishError('Instagram requires external_id and public asset URL')
  params={'access_token':self.token,'caption':payload.get('caption','')}
  params.update({'media_type':'REELS','video_url':asset['public_url']} if asset.get('kind')=='video' else {'image_url':asset['public_url']})
  r=httpx.post(f'{api}/{ig_id}/media',params=params,timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  creation=r.json().get('id'); r=httpx.post(f'{api}/{ig_id}/media_publish',params={'creation_id':creation,'access_token':self.token},timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('id'),'creation_id':creation}
class FacebookPublisher(Publisher):
 def publish(self,payload,asset=None):
  page=self.meta.get('external_id') or self.meta.get('page_id'); api=os.getenv('META_GRAPH_URL','https://graph.facebook.com/v24.0')
  if not page:raise PublishError('Facebook requires page_id/external_id')
  if asset and asset.get('public_url'):
   path='videos' if asset.get('kind')=='video' else 'photos'; data={'file_url' if path=='videos' else 'url':asset['public_url'],'description' if path=='videos' else 'caption':payload.get('caption',''),'access_token':self.token}
   r=httpx.post(f'{api}/{page}/{path}',data=data,timeout=self.timeout)
  else:r=httpx.post(f'{api}/{page}/feed',data={'message':payload.get('caption',''),'access_token':self.token},timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('post_id') or r.json().get('id')}
class ThreadsPublisher(Publisher):
 def publish(self,payload,asset=None):
  user=self.meta.get('external_id') or self.meta.get('threads_user_id'); base=os.getenv('THREADS_API_URL','https://graph.threads.net')
  if not user:raise PublishError('Threads requires external_id')
  p={'text':payload.get('caption',''),'access_token':self.token,'media_type':'TEXT'}
  if asset and asset.get('public_url'):p.update({'media_type':'IMAGE','image_url':asset['public_url']} if asset.get('kind')=='image' else {'media_type':'VIDEO','video_url':asset['public_url']})
  r=httpx.post(f'{base}/{user}/threads',params=p,timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  cid=r.json().get('id'); r=httpx.post(f'{base}/{user}/threads_publish',params={'creation_id':cid,'access_token':self.token},timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('id'),'creation_id':cid}
class TikTokPublisher(Publisher):
 def publish(self,payload,asset=None):
  if not asset or not asset.get('public_url'):raise PublishError('TikTok requires public asset URL')
  base='https://open.tiktokapis.com/v2'; h={**self.headers(),'Content-Type':'application/json; charset=UTF-8'}
  info=httpx.post(f'{base}/post/publish/creator_info/query/',headers=h,json={},timeout=self.timeout)
  if info.status_code>=400:raise PublishError(info.text)
  privacy=(info.json().get('data',{}).get('privacy_level_options') or ['SELF_ONLY'])[0]
  if asset.get('kind')=='image': body={'post_info':{'title':payload.get('caption',''),'description':payload.get('caption',''),'privacy_level':privacy,'disable_comment':False,'auto_add_music':False},'source_info':{'source':'PULL_FROM_URL','photo_cover_index':0,'photo_images':[asset['public_url']]},'post_mode':'DIRECT_POST','media_type':'PHOTO'}
  else: body={'post_info':{'title':payload.get('caption',''),'privacy_level':privacy,'disable_comment':False,'disable_duet':False,'disable_stitch':False},'source_info':{'source':'PULL_FROM_URL','video_url':asset['public_url']}}
  endpoint='photo' if asset.get('kind')=='image' else 'video'
  r=httpx.post(f'{base}/post/publish/{endpoint}/init/',headers=h,json=body,timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'publish_id':r.json().get('data',{}).get('publish_id')}
class YouTubePublisher(Publisher):
 def publish(self,payload,asset=None):
  if not asset or not asset.get('bytes'):raise PublishError('YouTube requires video bytes')
  meta={'snippet':{'title':payload.get('title','AI Influencer Video'),'description':payload.get('caption',''),'tags':payload.get('hashtags',[])},'status':{'privacyStatus':payload.get('privacy_status','private')}}
  boundary='tf-boundary'; body=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n').encode()+asset['bytes']+f'\r\n--{boundary}--\r\n'.encode()
  r=httpx.post('https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status&uploadType=multipart',headers={**self.headers(),'Content-Type':f'multipart/related; boundary={boundary}'},content=body,timeout=600)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('id')}
class LinkedInPublisher(Publisher):
 def publish(self,payload,asset=None):
  author=self.meta.get('author_urn') or self.meta.get('external_id')
  if not author:raise PublishError('LinkedIn requires author_urn/external_id')
  h={**self.headers(),'Content-Type':'application/json','Linkedin-Version':os.getenv('LINKEDIN_VERSION','202606'),'X-Restli-Protocol-Version':'2.0.0'}
  body={'author':author,'commentary':payload.get('caption',''),'visibility':'PUBLIC','distribution':{'feedDistribution':'MAIN_FEED','targetEntities':[],'thirdPartyDistributionChannels':[]},'lifecycleState':'PUBLISHED','isReshareDisabledByAuthor':False}
  r=httpx.post('https://api.linkedin.com/rest/posts',headers=h,json=body,timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.headers.get('x-restli-id') or r.json().get('id')}
class XPpublisher(Publisher):
 def publish(self,payload,asset=None):
  r=httpx.post('https://api.x.com/2/tweets',headers={**self.headers(),'Content-Type':'application/json'},json={'text':payload.get('caption','')},timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('data',{}).get('id')}
class PinterestPublisher(Publisher):
 def publish(self,payload,asset=None):
  board=self.meta.get('board_id')
  if not board or not asset or not asset.get('public_url'):raise PublishError('Pinterest requires board_id and public asset URL')
  body={'board_id':board,'title':payload.get('title',''),'description':payload.get('caption',''),'media_source':{'source_type':'image_url','url':asset['public_url']}}
  r=httpx.post('https://api.pinterest.com/v5/pins',headers={**self.headers(),'Content-Type':'application/json'},json=body,timeout=self.timeout)
  if r.status_code>=400:raise PublishError(r.text)
  return {'platform_id':r.json().get('id')}
FACTORIES={'instagram':InstagramPublisher,'facebook':FacebookPublisher,'threads':ThreadsPublisher,'tiktok':TikTokPublisher,'youtube':YouTubePublisher,'linkedin':LinkedInPublisher,'x':XPpublisher,'pinterest':PinterestPublisher}
def publisher_for(account,token):
 cls=FACTORIES.get(account.platform)
 if not cls:raise PublishError(f'Unsupported platform: {account.platform}')
 return cls(account,token,account.metadata_json)
