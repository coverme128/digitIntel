"""Exchange sessions are explicit input, including holidays/early closes.
No guessing a business calendar. Missing coverage blocks qualification.
"""
from .util import dt
from zoneinfo import ZoneInfo


def classify_session(timestamp, calendar):
    instant = dt(timestamp)
    local_day = instant.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if not calendar or not calendar.get('start') or not calendar.get('end'):
        return {'session': 'UNKNOWN', 'complete': False}
    if not calendar['start'] <= local_day <= calendar['end']:
        return {'session': 'UNKNOWN', 'complete': False}
    sessions = sorted(calendar.get('sessions', []), key=lambda x: x['open'])
    day = next((s for s in sessions if dt(s['open']).astimezone(ZoneInfo('America/New_York')).date().isoformat() == local_day), None)
    next_day = next((s for s in sessions if dt(s['open']) > instant), None)
    prev_day = next((s for s in reversed(sessions) if dt(s['close']) < instant), None)
    if day:
        if instant < dt(day['open']):
            label, anchor = 'PREMARKET', prev_day and prev_day['close']
        elif instant < dt(day['close']):
            label, anchor = 'REGULAR', timestamp
        else:
            label, anchor = 'AFTER_HOURS', day['close']
    else:
        label, anchor = 'NON_TRADING', prev_day and prev_day['close']
    complete = bool(anchor) and (label == 'REGULAR' or bool(next_day))
    return {'session': label, 'anchor_at': anchor, 'next_open': next_day and next_day['open'], 'complete': complete}


def trading_age(event_at, as_of, calendar):
    a, b = dt(event_at), dt(as_of)
    if b < a or not classify_session(event_at, calendar)['complete'] or not classify_session(as_of, calendar)['complete']:
        return None
    return sum(a < dt(s['close']) <= b for s in calendar['sessions'])


def exchange_calendar(start, end):
    """Versioned XNYS sessions, including historical exceptions and early closes."""
    from datetime import date
    from .util import DomainError
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b or (b-a).days>730:raise DomainError('Calendar range must be ordered and at most 730 days')
    try:
        import exchange_calendars as xcals
        exchange=xcals.get_calendar('XNYS',start=start,end=end)
        sessions=[{'open':exchange.session_open(label).isoformat(),'close':exchange.session_close(label).isoformat()} for label in exchange.sessions_in_range(start,end)]
        return {'start':start,'end':end,'source':'exchange_calendars/XNYS','version':xcals.__version__,'sessions':sessions}
    except ImportError:raise DomainError('Install requirements-integrations.txt for the exchange calendar','DEPENDENCY_MISSING',409) from None
