from __future__ import annotations
import os, uuid
import boto3
from botocore.client import Config
class Storage:
    def __init__(self):
        self.bucket=os.getenv('S3_BUCKET','trendflow-assets')
        self.client=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT','http://minio:9000'),aws_access_key_id=os.getenv('S3_ACCESS_KEY','trendflow'),aws_secret_access_key=os.getenv('S3_SECRET_KEY','change-me-now'),region_name=os.getenv('S3_REGION','us-east-1'),config=Config(signature_version='s3v4'))
    def ensure(self):
        try:self.client.head_bucket(Bucket=self.bucket)
        except Exception:self.client.create_bucket(Bucket=self.bucket)
    def put(self,data:bytes,content_type:str,prefix='generated'):
        self.ensure(); key=f'{prefix}/{uuid.uuid4().hex}'; self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType=content_type); return f's3://{self.bucket}/{key}'
    def get(self,uri:str)->bytes:
        if not uri.startswith('s3://'):raise ValueError('Only s3:// assets supported')
        bucket,key=uri[5:].split('/',1); return self.client.get_object(Bucket=bucket,Key=key)['Body'].read()