"""Redact obvious contact details and credentials before model calls or storage."""
import re
import unicodedata

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_PHONE = re.compile(r'(?<!\w)(?:(?:\+98|0098)[\s().-]*|0[\s().-]*)?9(?:[\s().-]*\d){9}(?!\d)|(?<!\d)0(?:[\s().-]*\d){10}(?!\d)')
_CODE = re.compile(
    r'((?:کد(?:[\s\u200c]*(?:تأیید|تایید|ورود|یک[\s\u200c-]*بار[\s\u200c-]*مصرف))?'
    r'|\botp\b|\bverification[\s-]+code\b|\bone[\s\u2010-\u2015-]*time[\s-]+pass[\s-]*code\b)'
    r'\s*(?:(?:من|my)\s*)?[:=：-]?\s*(?:(?:is|است)\s*)?)'
    r'(\d(?:[ -]*\d){3,7})(?![ -]*\d)', re.I,
)
_PASSWORD = re.compile(
    r'((?<!\w)(?:رمز(?:[\s\u200c]*عبور)?|گذر[\s\u200c]*واژه|\bpassword\b|api[_ -]?key)\s*(?:من\s*)?'
    r'(?:[:=：-]\s*|(?:is|است)\s+|(?=[A-Za-z0-9_!@#$%^&*.-]*[0-9])))'
    r'(?!\[پوشانده شد\])([^\s،,؛;]+)',
    re.I,
)
_EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
_KEY = re.compile(r'\bsk-[A-Za-z0-9_-]{8,}\b')


def has_visible_text(text: str) -> bool:
    return any(unicodedata.category(char)[0] in 'LNPS' for char in text)


def redact(text: str) -> str:
    normalized = text.translate(_DIGITS)
    # Substitute by index so unrelated Persian digits and prose remain unchanged.
    matches = []
    for pattern in (_PHONE, _EMAIL, _KEY):
        matches.extend((m.start(), m.end()) for m in pattern.finditer(normalized))
    for pattern in (_CODE, _PASSWORD):
        matches.extend((m.start(2), m.end(2)) for m in pattern.finditer(normalized))
    if re.fullmatch(r'\s*\d{4,8}\s*', normalized):
        matches.append((0, len(text)))
    merged = []
    for start, end in sorted(matches):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start,end))
    for start, end in reversed(merged):
        # Ranges are applied to the original text; digit translation keeps length.
        text = text[:start] + '[پوشانده شد]' + text[end:]
    return text


def reject_sensitive(value: str) -> str:
    if redact(value) != value or '[پوشانده شد]' in value:
        raise ValueError('اطلاعات تماس یا رمز را فقط در فرم رسمی وارد کنید.')
    return value
