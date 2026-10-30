"""Reject unsupported numerical claims before anything reaches the screen or voice."""
import re
import math

NUMBER = re.compile(r'(?<![\w])([−-]?\$?\s*\d[\d,]*(?:\.\d+)?)(?:\s*(billion|million|thousand|[BMK])\b)?(\s*%)?',re.I)
WORDS = {w:i for i,w in enumerate('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split())}
WORDS.update(dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10))))
SCALES = {'hundred':100,'thousand':1000,'million':1000000,'billion':1000000000}
WORD_PATTERN = re.compile(r'\b(?:minus\s+|negative\s+)?(?:'+ '|'.join(WORDS)+r')(?:[\s-]+(?:'+ '|'.join(WORDS)+r'|hundred|thousand|million|billion|and|point))*\b(?:\s+percent)?',re.I)
def _word_numbers(text):
    for match in WORD_PATTERN.finditer(text):
        words=match.group().lower().replace('-',' ').split();negative=words[0] in ['minus','negative']
        if negative:words=words[1:]
        percent=words[-1]=='percent'
        if percent:words=words[:-1]
        scale=1
        if 'point' in words:
            index=words.index('point');after=words[index+1:]
            if after and after[-1] in ['thousand','million','billion']:scale=SCALES[after.pop()]
            if not after or any(w not in WORDS or WORDS[w]>9 for w in after):continue
            fraction=float('0.'+''.join(str(WORDS[w]) for w in after));words=words[:index];precision=len(after)
        else:fraction=0;precision=0
        subtotal=total=0
        for w in words:
            if w in WORDS:subtotal+=WORDS[w]
            elif w=='hundred':subtotal=max(1,subtotal)*100
            elif w in SCALES:total+=max(1,subtotal)*SCALES[w];subtotal=0
        value=(total+subtotal+fraction)*scale
        tolerance=.501*10**(-precision)*scale
        if negative:value=-value
        if percent:value/=100;tolerance/=100
        yield {'text':match.group(),'value':value,'tolerance':tolerance}
def _numbers(text):
    for match in NUMBER.finditer(text):
        raw=match.group(1).replace('$','').replace(',','').replace('−','-').replace(' ','')
        value=float(raw);unit=(match.group(2) or '').lower()
        scale={'b':1e9,'billion':1e9,'m':1e6,'million':1e6,'k':1e3,'thousand':1e3}.get(unit,1)
        percent=bool(match.group(3));decimals=len(raw.split('.')[-1]) if '.' in raw else 0
        tolerance=.501*(10**(-decimals))*scale
        if percent:value/=100;tolerance/=100
        yield {'text':match.group(0).strip(),'value':value*scale,'tolerance':tolerance}
def _collect(obj):
    if isinstance(obj,bool) or obj is None:return []
    if isinstance(obj,(int,float)):return [float(obj)]
    if isinstance(obj,str):return [x['value'] for x in _numbers(obj)]
    if isinstance(obj,dict):return [x for v in obj.values() for x in _collect(v)]
    if isinstance(obj,list):return [x for v in obj for x in _collect(v)]
    return []
def check(answer,tool_output):
    # Values, parameters and period labels are outputs of deterministic tools.
    evidence={k:tool_output.get(k) for k in ['values','method','sources','chart']}
    allowed=_collect(evidence)
    # Quarter/fiscal labels carry numbers after a letter, outside the word-boundary regex.
    context=[]
    for match in re.finditer(r'\b(?:Q|FY)(\d+)\b',answer,re.I):
        n=float(match.group(1));context.append({'text':match.group(0),'value':n,'tolerance':0})
    extracted=list(_numbers(answer))+list(_word_numbers(answer))+context
    unsupported=[n['text'] for n in extracted if not any(math.isfinite(v) and abs(n['value']-v)<=n['tolerance'] for v in allowed)]
    # Preserve literal entity names: a trailing deal identifier is not a count.
    entities=[]
    values=tool_output.get('values',{})
    for collection in ['deals','top_variance_deals']:
        for item in values.get(collection,[]):
            name=item.get('name','')
            base=name.rsplit(' · ',1)[0]
            if name and name in tool_output.get('answer','') and base in answer and name not in answer:entities.append(name)
    claim_errors=[]
    if tool_output.get('tool') in ['forecast_quarter','board_summary']:
        for label,key in [('revenue','revenue'),('(?:operating )?profit','profit')]:
            for match in re.finditer(r'\b'+label+r'\b[^.$\d]{0,35}(\$[\d,.]+\s*(?:[BMK]\b|million|billion)?)',answer,re.I):
                if re.search(r'\b(?:range|interval)\b',match.group(0),re.I):continue
                number=next(_numbers(match.group(1)),None)
                if number and abs(number['value']-values[key])>number['tolerance']:claim_errors.append(match.group(0))
    return {'passed':not unsupported and not entities and not claim_errors,'checked':len(extracted),'unsupported':unsupported,'missing_entities':entities,'claim_errors':claim_errors,'numbers':[n['text'] for n in extracted]}
def grounded_answer(candidate,tool_output):
    report=check(candidate,tool_output)
    if report['passed']:return candidate,{**report,'fallback':False}
    answer=tool_output['answer'];fallback=check(answer,tool_output)
    if not fallback['passed']:
        raise ValueError(f'Unverified deterministic template: {fallback["unsupported"]}')
    return answer,{**fallback,'fallback':True,'rejected_numbers':report['unsupported']}
