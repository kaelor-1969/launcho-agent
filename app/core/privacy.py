"""Redact obvious contact details and credentials before model calls or storage."""
import re

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_PHONE = re.compile(r'(?<!\w)(?:(?:\+98|0098)[\s().-]*|0[\s().-]*)?9(?:[\s().-]*\d){9}(?!\d)|(?<!\d)0(?:[\s().-]*\d){10}(?!\d)')
_CODE = re.compile(r'((?:کد(?:\s*(?:تأیید|تایید|ورود|یک.?بار.?مصرف))?|otp|verification\s*code)\s*(?:من\s*)?[:=：-]?\s*(?:(?:is|است)\s*)?)(\d(?:[ -]*\d){3,7})(?!\d)', re.I)
_PASSWORD = re.compile(r'((?:رمز(?:\s*عبور)?|password|api[_ -]?key)\s*(?:من\s*)?[:=：-]?\s*(?:(?:is|است)\s*)?)([^\s،,؛;]+)', re.I)
_EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
_KEY = re.compile(r'\bsk-[A-Za-z0-9_-]{8,}\b')


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
