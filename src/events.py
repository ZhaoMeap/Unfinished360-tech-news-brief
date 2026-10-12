"""Identity matching is deliberately stricter than thematic similarity."""
import re
from difflib import SequenceMatcher
from .community import canonical
from .evidence import event_id, coverage


def normalized(title):
    return re.sub(r'[^\w\u4e00-\u9fff]+',' ',title.lower()).strip()


def same_event(a,b):
    if canonical(a.url)==canonical(b.url):
        return True
    left,right=normalized(a.title),normalized(b.title)
    if left==right and left:
        return True
    if len(left)<25 or len(right)<25:
        return False
    if re.findall(r'\d+(?:\.\d+)?',left)!=re.findall(r'\d+(?:\.\d+)?',right):
        return False
    actions=r'\b(?:not|no|fails?|halts?|stops?|cuts?|increases?|decreases?|launch\w*|patch\w*|acquir\w*)\b|停止|增加|減少|修補'
    if set(re.findall(actions,left))!=set(re.findall(actions,right)):
        return False
    return SequenceMatcher(None,left,right).ratio()>=.92
