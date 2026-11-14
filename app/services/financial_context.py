"""Conservative financial intent for the internal offer contract; no pricing claims."""
import re


def normalized(text):
    return ' '.join(str(text).translate(str.maketrans('يك', 'یک')).replace('\u200c', ' ').split())


def financial_context(message, history=None):
    text = normalized(message)
    turns = history or []
    shown = any(turn.get('role') == 'assistant' and any(
        label in turn.get('content', '') for label in ('پیشنهاد آزمایشی', 'پیشنهاد لانچو')
    ) for turn in turns)
    # A rejection persists only until the user explicitly asks to reconsider.
    rejected = False
    for turn in [*turns, {'role': 'user', 'content': message}]:
        if turn.get('role') != 'user':
            continue
        content = normalized(turn.get('content', ''))
        if re.search(r'پیشنهاد.*(?:نمی خوام|نمی خواهم|نمیخوام|نکن|نده)|اقساط.*(?:نمی خوام|نمی خواهم|نمیخوام)', content):
            rejected = True
        elif re.search(r'دوباره.*(?:پیشنهاد|اقساط)|(?:پیشنهاد|اقساط).*دوباره', content):
            rejected = False
    negated = bool(re.search(r'(?:گران|گرون|زیاد|بالا)\s*نیست|مشکل\s*(?:مالی|بودجه|هزینه).*ندار|بودجه\s*دارم', text))
    objection = not negated and bool(re.search(
        r'گران|گرون|گرونه|بودجه\s*(?:ندار|کمه|کم است)|پول\s*ندار|نمی تونم.*پرداخت|نمی توانم.*پرداخت|'
        r'(?:هزینه|قیمت).{0,20}(?:بالا|زیاد|سنگین)', text))
    installments = bool(re.search(r'اقساط|قسطی|قسط|پیش پرداخت|یکجا.*(?:نمی تونم|نمی توانم)', text))
    return {
        'objections': ['price'] if objection or installments else [],
        'needs': ['low_upfront'] if installments and not rejected else [],
        'discountAlreadyShown': shown,
        'rejected': rejected,
    }
