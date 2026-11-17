"""Only activate a separately validated historical revision; original snapshot unchanged."""
import json
from pathlib import Path
from hashlib import sha256
from decimal import Decimal
PROJECT=Path(__file__).resolve().parents[1]
_cache={}

def active():
    pointer=PROJECT/'config/history_active.json'
    if not pointer.exists():return None,None
    try:
        tag=pointer.stat().st_mtime_ns
        if _cache.get('tag')==tag:
            folder,quality=_cache['value'];st=(folder/'quality.json').stat()
            if _cache.get('quality_tag')==(st.st_mtime_ns,st.st_size):return folder,quality
        p=json.loads(pointer.read_text())
        folder=(PROJECT/p['folder']).resolve()
        if not folder.is_relative_to(PROJECT/'data'):raise ValueError('History outside data')
        path=folder/'quality.json';raw=path.read_bytes()
        if sha256(raw).hexdigest()!=p['quality_sha256']:raise ValueError('History quality hash mismatch')
        quality=json.loads(raw)
        if quality['validation_status']!='PASS':raise ValueError('Unvalidated history')
        st=path.stat();_cache.update(tag=tag,quality_tag=(st.st_mtime_ns,st.st_size),value=(folder,quality))
        return folder,quality
    except FileNotFoundError as error:raise ValueError('Active history revision is incomplete') from error

def info():
    folder,q=active()
    return {'start':q['query_start'],'end':q['query_end'],'actual_first':q['first'],'actual_last':q['last'],'revision':folder.name} if q else {'start':'2026-01-01','end':'2026-11-04','actual_first':'2026-01-05','actual_last':'2026-11-04','revision':'ssi_universe_20261104'}

def read_verified(path,expected=None):
    raw=path.read_bytes()
    digest=sha256(raw).hexdigest()
    if digest!=path.with_suffix('.sha256').read_text() or (expected is not None and digest!=expected):raise ValueError('History file checksum mismatch')
    return json.loads(raw)

def rows(symbol):
    folder,q=active()
    if folder is None:return None
    if symbol not in q['symbols_requested']:return None
    path=folder/'symbols'/f'{symbol}.json'
    if not path.exists():return []
    return read_verified(path,q['file_sha256'][str(path.relative_to(folder))])['rows']

def index_data(code):
    folder,q=active()
    if folder is None:return None
    path=folder/'index_ohlc'/f'{code}.json'
    if not path.exists():return None
    saved=read_verified(path,q['file_sha256'][str(path.relative_to(folder))]);result=[];previous=None
    for r in saved['rows']:
        close=Decimal(r['close_vnd']);change=close-previous if previous else None
        result.append({'tradingDate':r['date'].replace('-','/'),'indexValue':str(close),
                       'open':r.get('open_vnd'),'high':r.get('high_vnd'),'low':r.get('low_vnd'),
                       'indexChange':str(change) if change is not None else None,
                       'indexChangePercentage':str(change/previous*100) if change is not None else None})
        previous=close
    return {'code':code,'rows':result,'source':'SSI official daily index OHLC','units':'index points',
            'derivation':'Close-to-close changes computed from official index OHLC; not intraday summary or stock-synthesized index.'}
