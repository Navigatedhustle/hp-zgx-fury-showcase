"""Always available deterministic language routing and bounded scenario parameters."""
import re
from atlas.data.generate import REGIONS

def route(question,persona='enterprise'):
    q=question.casefold().replace('’',"'")
    kwargs={}
    for region in REGIONS:
        if re.search(r'\b'+region.lower()+r'\b',q):kwargs['region']=region;break
    if any(x in q for x in ['send me','export','brief card','save that']):return 'export_brief',{}
    if any(x in q for x in ['center','centre','site','phoenix','denver','albuquerque']):
        cities=[c for c in ['Phoenix','Denver','Albuquerque','Austin','Salt Lake City'] if c.casefold() in q]
        return 'score_sites',{'persona':persona,**({'cities':cities} if len(cities)>=2 else {})}
    if persona=='university':
        if any(x in q for x in ['enroll','yield','admission','student','fall']):return 'enrollment_forecast',{}
        if any(x in q for x in ['sponsor','dependent','dependence','concentration']):return 'sponsor_concentration',{}
        if any(x in q for x in ['grant','funding','research','fy27','fy 27','fiscal']):return 'grant_forecast',{}
        return None,{}
    if any(x in q for x in ['board','thirty second','30 second','summary']):return 'board_summary',{}
    if any(x in q for x in ['win rate','commit stage','what if','what happens','drops','drop ','decrease']):
        m=re.search(r'(\d+(?:\.\d+)?)\s*(?:percentage\s*)?(?:points?|percent|%)',q)
        n=float(m.group(1)) if m else 10 if 'ten' in q else 5 if 'five' in q else 10
        return 'what_if',{**kwargs,'commit_drop':min(1,max(0,n/100))}
    if any(x in q for x in ['risk','at risk','deals','exposure']):return 'deal_risk',kwargs
    if any(x in q for x in ['hire','hiring','reps','headcount']):return 'hiring_plan',{}
    if any(x in q for x in ['coverage','last year','year ago']):return 'pipeline_coverage',{}
    if any(x in q for x in ['behind','plan','region','shortfall']):return 'region_vs_plan',{}
    if any(x in q for x in ['revenue','profit','forecast','projected','quarter','q4','q 4']):return 'forecast_quarter',kwargs
    return None,{}
