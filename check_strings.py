import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

for m in re.finditer(r'\"([^\"]+)\"', text):
    t = m.group(1).strip()
    if any(c.isalpha() for c in t) and ' ' in t and not '{' in t and not '\\n' in t:
        print(t)
