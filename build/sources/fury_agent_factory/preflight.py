from pathlib import Path
from dotenv import load_dotenv
import httpx
from engine import Settings
load_dotenv(Path(__file__).with_name('.env'))
s=Settings.from_env()
s.validate()
headers={'Authorization':'Bearer '+s.api_key} if s.api_key else {}
with httpx.Client(timeout=15,trust_env=False,follow_redirects=False) as client:
    response=client.get(s.base_url+'/models',headers=headers)
    response.raise_for_status()
    models=[m['id'] for m in response.json().get('data',[])]
    print('Declared inference location:',s.location)
    print('Served models:',models)
    if s.model not in models:
        raise SystemExit('Configured model not listed. Correct FURY_MODEL or verify server aliases.')
    print('Model found. Next run one workflow and verify usage and output.')
