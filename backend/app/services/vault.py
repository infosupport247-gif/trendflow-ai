import os
from cryptography.fernet import Fernet
class TokenVault:
    def __init__(self):
        raw=os.getenv('TOKEN_VAULT_KEY','').strip(); self.fernet=Fernet(raw.encode()) if raw else None
    def require(self):
        if not self.fernet:raise RuntimeError('TOKEN_VAULT_KEY is not configured')
    def encrypt(self,value):self.require(); return self.fernet.encrypt(value.encode()).decode()
    def decrypt(self,value):self.require(); return self.fernet.decrypt(value.encode()).decode()