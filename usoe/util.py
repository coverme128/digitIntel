from __future__ import annotations
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal, ROUND_FLOOR

ROOT = Path(__file__).resolve().parent.parent

def load_env():
    p = ROOT / '.env'
    if p.exists():
        for line in p.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def dt(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return result

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def digest(value):
    data = value if isinstance(value, bytes) else canonical(value).encode()
    return hashlib.sha256(data).hexdigest()

def number(value, name='value', positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if positive and value <= 0:
        raise ValueError(f'{name} must be positive')
    return float(value)

def floor_ratio(a, b):
    return int((Decimal(str(a)) / Decimal(str(b))).to_integral_value(rounding=ROUND_FLOOR))

def money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01')))

def read_rules():
    return json.loads((ROOT / 'config/rules-1.0.2.json').read_text())

class DomainError(ValueError):
    def __init__(self, message, code='VALIDATION_ERROR', status=400):
        super().__init__(message)
        self.code, self.status = code, status
