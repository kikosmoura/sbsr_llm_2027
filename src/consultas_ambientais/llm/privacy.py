"""Redacao antes de prompts/logs; nao abre .env ou qualquer cofre."""
import os
import re

class Redactor:
    def __init__(self,secrets=()):
        self.secrets=sorted({s for s in secrets if isinstance(s,str) and len(s)>=3},key=len,reverse=True)

    @classmethod
    def from_environment(cls,settings):
        values=[]
        for name in ["client_id","client_secret","scope","audience","base_url","token_url"]:
            value=getattr(settings,name,None)
            if value:values.append(value.get_secret_value())
        for name in ["SOURCE_PG_HOST","SOURCE_PG_DATABASE","SOURCE_PG_USER","SOURCE_PG_PASSWORD"]:
            if os.environ.get(name):values.append(os.environ[name])
        return cls(values)

    def clean(self,text):
        changes=[]
        for secret in self.secrets:
            if secret in text:text=text.replace(secret,"[REDIGIDO]");changes.append("valor_configurado")
        patterns=[("autorizacao",r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"),
            ("bearer",r"(?i)\bbearer\s+[^\s,;]+"),
            ("credencial",r"(?i)\b(?:password|senha|client_secret|client_id|access_token|refresh_token|username|user|usuario|usuário|host|hostname|database|banco|porta|port|SOURCE_PG_[A-Z_]+|LLM_[A-Z_]+)\s*[:=]\s*[^\s,;]+"),
            ("conexao",r"(?i)(?:postgres(?:ql)?|mysql)://[^\s]+"),
            ("ip_privado",r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"),
            ("url_assinada",r"https?://[^\s]*(?:X-Amz-Signature|access_token|signature)=[^\s]*"),
            ("jwt",r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")]
        for label,pattern in patterns:
            text,count=re.subn(pattern,"[REDIGIDO]",text)
            if count:changes.append(label)
        return text,sorted(set(changes))

    def model_name(self,value):
        if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}",value) or "://" in value:return None
        clean,changes=self.clean(value)
        return None if changes else clean
