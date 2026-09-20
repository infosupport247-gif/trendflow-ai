from __future__ import annotations
import httpx,os
class AnalyticsError(RuntimeError):pass
def collect(platform,token,meta,platform_id=None):
    h={'Authorization':f'Bearer {token}'}
    if platform=='youtube' and platform_id:
        r=httpx.get('https://www.googleapis.com/youtube/v3/videos',headers=h,params={'part':'statistics,snippet','id':platform_id},timeout=60)
        if r.status_code>=400:raise AnalyticsError(r.text)
        return ((r.json().get('items') or [{}])[0]).get('statistics',{})
    if platform=='x' and platform_id:
        r=httpx.get(f'https://api.x.com/2/tweets/{platform_id}',headers=h,params={'tweet.fields':'public_metrics,created_at'},timeout=60)
        if r.status_code>=400:raise AnalyticsError(r.text)
        return r.json().get('data',{}).get('public_metrics',{})
    if platform=='instagram' and platform_id:
        base=os.getenv('META_GRAPH_URL','https://graph.facebook.com/v24.0')
        r=httpx.get(f'{base}/{platform_id}/insights',params={'metric':'impressions,reach,likes,comments,saved,shares','access_token':token},timeout=60)
        if r.status_code>=400:raise AnalyticsError(r.text)
        return {x.get('name'):x.get('values',[{}])[-1].get('value') for x in r.json().get('data',[])}
    return {'status':'collector_not_configured_for_platform','platform':platform}