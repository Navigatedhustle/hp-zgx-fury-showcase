"""MIT. English cardinal/ordinal rendering for deterministic speech formatting."""
from decimal import Decimal
SMALL='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS='zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()
def integer(n):
 n=int(n)
 if n<0:return 'minus '+integer(-n)
 if n<20:return SMALL[n]
 if n<100:return TENS[n//10]+(' '+SMALL[n%10] if n%10 else '')
 if n<1000:return SMALL[n//100]+' hundred'+(' '+integer(n%100) if n%100 else '')
 for scale,name in [(10**12,'trillion'),(10**9,'billion'),(10**6,'million'),(1000,'thousand')]:
  if n>=scale:return integer(n//scale)+' '+name+(' '+integer(n%scale) if n%scale else '')
 raise ValueError('Unsupported number')
def num2words(value,to='cardinal',**kwargs):
 s=format(Decimal(str(value)),'f');negative=s.startswith('-');s=s.lstrip('-');parts=s.split('.')
 result=integer(int(parts[0]))
 if len(parts)>1:result+=' point '+' '.join(SMALL[int(c)] for c in parts[1])
 if to=='ordinal':
  irregular={'zero':'zeroth','one':'first','two':'second','three':'third','five':'fifth','eight':'eighth','nine':'ninth','twelve':'twelfth'}
  words=result.split();last=words[-1];words[-1]=irregular.get(last,last[:-1]+'ieth' if last.endswith('y') else last+'th');result=' '.join(words)
 return ('minus ' if negative else '')+result
