# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit import reasonableness_check as R
cases = {
    '12.3%': 0.123,
    '1.2亿元': 1.2e8,
    '150.80元': 150.80,
    '5万': 5e4,
    '41.49%': 0.4149,
    '3.30亿': 3.30e8,
    '': None,
    '-': None,
    '—': None,
    '1,640.00': 1640.00,
}
bad = []
for k, v in cases.items():
    got = R._parse_num(k)
    ok = (got is None and v is None) or (got is not None and v is not None and abs(got - v) <= 1e-9 * max(abs(got), abs(v), 1.0))
    if not ok:
        bad.append('%r -> %r (期望 %r)' % (k, got, v))
    print('%r -> %r 期望 %r  %s' % (k, got, v, 'PASS' if ok else 'FAIL'))
print('RESULT:', 'PASS' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
