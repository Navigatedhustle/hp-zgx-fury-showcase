"""Commercial-safe local voice: Kokoro ONNX with a BSD pronunciation dictionary.

No phonemizer service, browser speech API, or automatic model downloads.
"""
import io
import json
import re
import threading
import time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from atlas.config import ROOT

ONES='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS='zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
def number_words(n):
    if n<0:return 'minus '+number_words(-n)
    if n<20:return ONES[n]
    if n<100:return TENS[n//10]+(' '+ONES[n%10] if n%10 else '')
    for scale,name in [(1000000000,'billion'),(1000000,'million'),(1000,'thousand'),(100,'hundred')]:
        if n>=scale:return number_words(n//scale)+' '+name+(' '+number_words(n%scale) if n%scale else '')
def normalize(text):
    text=text.replace('−','minus ').replace('×',' times ').replace('·',', ')
    text=re.sub(r'\bQ([1-4])\b',lambda m:'quarter '+number_words(int(m[1])),text)
    text=re.sub(r'\bFY\s?(\d+)\b',lambda m:'fiscal year '+m[1],text)
    pattern=re.compile(r'(\$)?(\d[\d,]*(?:\.\d+)?)([MBK])?(%)?')
    def convert(m):
        raw=m[2].replace(',','');whole,_,fraction=raw.partition('.')
        spoken=number_words(int(whole))
        if fraction:spoken+=' point '+' '.join(ONES[int(c)] for c in fraction)
        if m[3]:spoken+=' '+{'M':'million','B':'billion','K':'thousand'}[m[3]]
        if m[4]:spoken+=' percent'
        if m[1]:spoken+=' dollars'
        return spoken
    return pattern.sub(convert,text)

ARPABET={'AA':'ɑ','AE':'æ','AH':'ʌ','AO':'ɔ','AW':'aʊ','AY':'aɪ','B':'b','CH':'ʧ','D':'d','DH':'ð','EH':'ɛ','ER':'ɜɹ','EY':'eɪ','F':'f','G':'ɡ','HH':'h','IH':'ɪ','IY':'i','JH':'ʤ','K':'k','L':'l','M':'m','N':'n','NG':'ŋ','OW':'oʊ','OY':'ɔɪ','P':'p','R':'ɹ','S':'s','SH':'ʃ','T':'t','TH':'θ','UH':'ʊ','UW':'u','V':'v','W':'w','Y':'j','Z':'z','ZH':'ʒ'}
class Voice:
    def __init__(self):
        self.loaded=False;self.session=None;self.last_ms=None;self.lock=threading.Lock();self.voices={}
    def load(self):
        meta=ROOT/'models/kokoro-onnx.json'
        if not meta.exists():return
        root=Path(json.loads(meta.read_text())['path']);self.vocab=json.loads((root/'tokenizer.json').read_text())['model']['vocab']
        self.dictionary={}
        for line in (ROOT/'models/cmudict.dict').read_text().splitlines():
            if line.startswith(';;;'):continue
            parts=line.split()
            if len(parts)>1 and '(' not in parts[0]:self.dictionary[parts[0]]=parts[1:]
        options=ort.SessionOptions();options.intra_op_num_threads=6;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(root/'onnx/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.voices={name:np.fromfile(root/f'voices/{name}.bin',dtype=np.float32).reshape(-1,1,256) for name in ['af_heart','am_adam']}
        self.loaded=True;self.synthesize('Ready to answer your executive questions.')
    def phonemes(self,text):
        out=[]
        for word in re.findall(r"[a-z]+(?:'[a-z]+)?|[.,!?;:]",normalize(text).lower()):
            if len(word)==1 and word in '.,!?;:':out.append(word);continue
            phones=self.dictionary.get(word)
            if phones is None:
                # Unlisted fictional names are spelled aloud; never fetch an external G2P model.
                phones=[p for c in word for p in self.dictionary.get(c,[])]
            phonemes=[]
            for p in phones:
                stress=p[-1] if p[-1:].isdigit() else '';key=p[:-1] if stress else p
                ipa=ARPABET.get(key,'')
                if stress=='0' and key=='AH':ipa='ə'
                if stress=='0' and key=='ER':ipa='ɚ'
                phonemes.append(('ˈ' if stress=='1' else 'ˌ' if stress=='2' else '')+ipa)
            out.append(''.join(phonemes))
        return ' '.join(out)
    def synthesize(self,text,voice='af_heart'):
        if not self.loaded:raise RuntimeError('Local voice has not loaded')
        start=time.perf_counter();phones=self.phonemes(text)
        tokens=[self.vocab[c] for c in phones if c in self.vocab]
        if len(tokens)>508:raise ValueError('Speak one short sentence at a time')
        input_ids=np.array([[0,*tokens,0]],dtype=np.int64);style=self.voices.get(voice,self.voices['af_heart'])[min(len(tokens)-1,509)]
        with self.lock:
            samples=self.session.run(None,{'input_ids':input_ids,'style':style,'speed':np.array([1.0],dtype=np.float32)})[0]
        self.last_ms=(time.perf_counter()-start)*1000
        return np.clip(samples.reshape(-1)*32767,-32768,32767).astype('<i2').tobytes()

voice=Voice()

async def synthesize_fast(text):
    """Use the warm GPU voice, with a warm CPU fallback at the same sample rate."""
    import asyncio
    import hashlib
    from atlas.speech import synthesize
    try:
        path,hit,elapsed=await synthesize(text)
        return path,hit,elapsed,'Kokoro 82M · GPU'
    except Exception:
        # Both alternatives are local. A sidecar failure must not break speech.
        pass
    normalized=normalize(text)
    key=hashlib.sha256(('kokoro-v1-cmu-v1|af_heart|'+normalized).encode()).hexdigest()
    path=ROOT/'artifacts/audio'/(key+'.pcm')
    path.parent.mkdir(exist_ok=True,parents=True)
    if path.exists():return path,True,0.0,'Kokoro 82M'
    if not voice.loaded:await asyncio.to_thread(voice.load)
    start=time.perf_counter()
    data=await asyncio.to_thread(voice.synthesize,text)
    temporary=path.with_suffix('.tmp');temporary.write_bytes(data);temporary.replace(path)
    return path,False,(time.perf_counter()-start)*1000,'Kokoro 82M'
