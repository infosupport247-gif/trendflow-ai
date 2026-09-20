from __future__ import annotations
import os, json, base64, tempfile
from typing import Any
import httpx
from openai import OpenAI

class AIError(RuntimeError): pass

class AIService:
    def __init__(self):
        self.key=os.getenv('OPENAI_API_KEY','').strip()
        self.text_model=os.getenv('OPENAI_TEXT_MODEL','gpt-5.6-luna')
        self.image_model=os.getenv('OPENAI_IMAGE_MODEL','gpt-image-2')
        self.tts_model=os.getenv('OPENAI_TTS_MODEL','gpt-4o-mini-tts')
        self.transcribe_model=os.getenv('OPENAI_TRANSCRIBE_MODEL','gpt-transcribe')
        self.client=OpenAI(api_key=self.key) if self.key else None
    def require(self):
        if not self.client: raise AIError('OPENAI_API_KEY is not configured')
        return self.client
    def text(self,prompt:str,system:str='')->str:
        r=self.require().responses.create(model=self.text_model,instructions=system or None,input=prompt); return r.output_text
    def json(self,prompt:str,system:str='')->dict:
        raw=self.text(prompt,system+'\nReturn valid JSON only.')
        try:return json.loads(raw)
        except Exception:
            a,b=raw.find('{'),raw.rfind('}')
            if a>=0 and b>a:return json.loads(raw[a:b+1])
            raise AIError('Model returned non-JSON output')
    def image(self,prompt:str,size:str='1024x1024')->bytes:
        r=self.require().images.generate(model=self.image_model,prompt=prompt,size=size); item=r.data[0]
        if getattr(item,'b64_json',None):return base64.b64decode(item.b64_json)
        if getattr(item,'url',None):return httpx.get(item.url,timeout=120).content
        raise AIError('Image provider returned no image payload')
    def speech(self,text:str,voice:str='alloy',fmt:str='mp3')->bytes:
        return self.require().audio.speech.create(model=self.tts_model,voice=voice,input=text,response_format=fmt).read()
    def transcribe(self,data:bytes,filename:str='audio.mp3')->str:
        f=tempfile.NamedTemporaryFile(suffix='-'+filename,delete=False); f.write(data); f.close()
        try:
            with open(f.name,'rb') as fh:return self.require().audio.transcriptions.create(model=self.transcribe_model,file=fh).text
        finally:os.unlink(f.name)