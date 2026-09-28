"""Deterministic canonical-boundary validators."""
import json
import re
from datetime import date
from .util import ROOT,number,DomainError

REGISTRY=json.loads((ROOT/'config/metric-registry.json').read_text())

def validate_fact(fact):
    metric=fact['metric_id'];unit=fact['unit'];value=fact['value']
    if metric not in REGISTRY['units']:raise DomainError('Metric is not registered: '+metric)
    if REGISTRY['units'][metric]!=unit:raise DomainError('Metric unit mismatch: '+metric)
    if unit=='boolean':
        if not isinstance(value,bool):raise DomainError('Boolean fact required: '+metric)
    elif unit=='text':
        if not isinstance(value,str) or not value.strip():raise DomainError('Non-empty text fact required: '+metric)
    else:number(value,metric)
    start=date.fromisoformat(fact['period_start']);end=date.fromisoformat(fact['period_end'])
    if start>end:raise DomainError('Invalid fact period')
    if isinstance(fact['fact_version'],bool) or not isinstance(fact['fact_version'],int) or fact['fact_version']<1:raise DomainError('Positive fact version required')
    if not re.fullmatch(r'[\w-]{1,180}',fact['fact_id']):raise DomainError('Invalid fact ID')


def json_pointer(data, pointer):
    if not pointer.startswith('/'):raise DomainError('JSON pointer must begin with /')
    current=data
    for part in pointer.split('/')[1:]:
        key=part.replace('~1','/').replace('~0','~')
        current=current[int(key)] if isinstance(current,list) else current[key]
    return current
