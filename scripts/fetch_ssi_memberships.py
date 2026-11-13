"""Current official index membership only; never historical eligibility."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.expand_ssi_market import cached,save,OUT
from src.ssi_client import SSIReadonly,safe_error
from src.universe import catalog
from hashlib import sha256

def main():
    client=SSIReadonly();members={};errors={}
    try:
        client.authenticate()
        for item in catalog()['indexes']:
            code=item['index']
            try:
                result=cached(client,'membership_'+sha256(code.encode()).hexdigest(),'/api/v3/data/securitiesByBoard',{'index':code})
                if not isinstance(result,list):raise ValueError('Invalid membership response')
                members[code]=sorted({r['symbol'] for r in result if r.get('symbol')})
            except Exception as e:errors[code]=safe_error(e)
        save(OUT/'memberships.json',{'current_members':members,'errors':errors,'historical':False})
        print(json.dumps({'indices':len(members),'errors':errors}))
    finally:client.close()

if __name__=='__main__':main()
