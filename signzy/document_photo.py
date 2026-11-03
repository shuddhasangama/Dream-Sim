"""Keep vendor photo references private; never fetch arbitrary returned URLs."""
from urllib.parse import urlsplit

HOSTS={'persist.wayne-rta.com','persist.signzy.tech','preproduction-persist.signzy.tech'}

def reference(body):
    result=body.get('result') if isinstance(body,dict) else None
    url=result.get('photo') if isinstance(result,dict) else None
    if not isinstance(url,str) or len(url)>4096 or any(ord(c)<33 for c in url): return None
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443): return None
        if not parsed.path.startswith('/api/files/') or '/download/' not in parsed.path: return None
    except ValueError: return None
    return {'url':url,'source':'digilocker_eaadhaar'}
