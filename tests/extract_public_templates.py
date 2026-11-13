"""Extract public template evidence from the saved official page (no signup IDs)."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
source = (root/'artifacts/review/official-home.html').read_text(encoding='utf8')
chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', source)
data = ''.join(json.loads(chunk) for chunk in chunks)
rows = [json.loads(item) for item in re.findall(r'\{"id":"[^"]+","title":.*?\}', data)
        if 'templateId' in item]
(root/'artifacts/review/public-templates.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps(rows, ensure_ascii=True, indent=2))
