"""Final public JSON boundary; never include auth material in local responses."""
from src.ssi_client import credentials

SENSITIVE={'apikey','apisecret','accesstoken','refreshtoken','authorization','privatekey','password','otp'}


def redact_public(value,secrets=None):
    if secrets is None:
        config=credentials()
        secrets=[config[k] for k in ['SSI_API_KEY','SSI_API_SECRET'] if config[k]]
    if isinstance(value,dict):
        return {key:'[REDACTED]' if str(key).lower().replace('_','').replace('-','') in SENSITIVE
                else redact_public(item,secrets) for key,item in value.items()}
    if isinstance(value,list):return [redact_public(item,secrets) for item in value]
    if isinstance(value,str):
        for secret in secrets:
            if secret:value=value.replace(secret,'[REDACTED]')
    return value
