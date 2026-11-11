"""Personal delivery policy, using Beijing calendar days and immutable daily claims."""
import hashlib,json,re
from datetime import datetime,timedelta
from .core import SHANGHAI

def preferences(user):
    time=user.get('send_time','08:00');frequency=user.get('frequency','daily')
    if not isinstance(time,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',time) or int(time[-2:])%5:raise ValueError('发送时间须为5分钟刻度')
    days=user.get('weekdays',list(range(7)))
    if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days):raise ValueError('发送星期无效')
    if frequency not in ('daily','weekdays','custom'):raise ValueError('发送频率无效')
    days=list(range(7)) if frequency=='daily' else list(range(5)) if frequency=='weekdays' else sorted(set(days))
    difficulty=user.get('difficulty','beginner');length=user.get('length','standard')
    if difficulty not in ('beginner','advanced') or length not in ('concise','standard'):raise ValueError('学习偏好无效')
    return dict(send_time=time,frequency=frequency,weekdays=days,difficulty=difficulty,length=length)

def content_key(user):
    p=preferences(user)
    return hashlib.sha256(json.dumps({'topics':sorted(set(t.strip().lower() for t in user['topics'])),'difficulty':p['difficulty'],'length':p['length']},sort_keys=True).encode()).hexdigest()[:24]

def scheduled(user,date):
    p=preferences(user)
    if date.weekday() not in p['weekdays']:return None
    hour,minute=map(int,p['send_time'].split(':'))
    slot=datetime.combine(date,datetime.min.time(),tzinfo=SHANGHAI).replace(hour=hour,minute=minute)
    return slot if slot.timestamp()>=user.get('schedule_effective_at',0) else None

def due(user,now):
    now=now.astimezone(SHANGHAI);slot=scheduled(user,now.date())
    return slot if slot and timedelta(0)<=now-slot<=timedelta(minutes=30) else None

def upcoming(user,now):
    now=now.astimezone(SHANGHAI)
    for offset in range(8):
        slot=scheduled(user,(now+timedelta(days=offset)).date())
        # Late delivery never crosses a Beijing calendar boundary.
        if slot and (slot>=now or offset==0 and now-slot<=timedelta(minutes=30)):return slot
    return None

def validate_profile(paper,user,today):
    from .core import validate_paper
    validate_paper(paper,today);p=preferences(user)
    if paper.get('learning_profile')!={k:p[k] for k in ('difficulty','length')}:raise ValueError('论文学习版本不匹配')
    count=len(re.findall(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*",paper['excerpt']))
    low,high=(100,110) if p['length']=='concise' else (130,150)
    if not low<=count<=high:raise ValueError('节选长度与偏好不匹配')
    if p['length']=='standard' and not re.search(r'[\u4e00-\u9fff]',paper.get('reading_guide','')):raise ValueError('标准版缺少阅读导引')
    if any(not re.search(r'[\u4e00-\u9fff]',term.get('explanation','')) for term in paper['terms']):raise ValueError('学习版缺少术语讲解')
    return paper
