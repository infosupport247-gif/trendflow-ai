from __future__ import annotations
import os,urllib.parse
class SocialError(RuntimeError):pass
PROVIDERS={
'instagram':{'env':'META_APP_ID','authorize':'https://www.facebook.com/v24.0/dialog/oauth','scope':'instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement'},
'facebook':{'env':'META_APP_ID','authorize':'https://www.facebook.com/v24.0/dialog/oauth','scope':'pages_show_list,pages_read_engagement'},
'youtube':{'env':'GOOGLE_CLIENT_ID','authorize':'https://accounts.google.com/o/oauth2/v2/auth','scope':'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'},
'tiktok':{'env':'TIKTOK_CLIENT_KEY','authorize':'https://www.tiktok.com/v2/auth/authorize/','scope':'user.info.basic,video.publish'},
'linkedin':{'env':'LINKEDIN_CLIENT_ID','authorize':'https://www.linkedin.com/oauth/v2/authorization','scope':'openid profile w_member_social'},
'x':{'env':'X_CLIENT_ID','authorize':'https://twitter.com/i/oauth2/authorize','scope':'tweet.read tweet.write users.read offline.access'},
'pinterest':{'env':'PINTEREST_APP_ID','authorize':'https://www.pinterest.com/oauth/','scope':'boards:read,pins:read,pins:write'},
'threads':{'env':'META_APP_ID','authorize':'https://www.facebook.com/dialog/oauth','scope':'threads_basic,threads_content_publish'}}
def auth_url(platform,state,redirect_uri):
    p=PROVIDERS.get(platform)
    if not p:raise SocialError('Unsupported platform')
    client=os.getenv(p['env'],'')
    if not client:raise SocialError(f"{p['env']} is not configured")
    params={'client_id':client,'redirect_uri':redirect_uri,'response_type':'code','state':state,'scope':p['scope']}
    if platform=='youtube':params.update(access_type='offline',prompt='consent')
    if platform=='tiktok':params.update(client_key=client);params.pop('client_id',None)
    return p['authorize']+'?'+urllib.parse.urlencode(params)