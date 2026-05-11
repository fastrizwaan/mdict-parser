import re

def KillSlashes(matchobj):
    if matchobj.group(1): return '\\'
    else: return ''

test_str = r'\[C\]'
print(f"Original: {test_str}")
result = re.sub(r'(\\\\\\\\)|(\\\\)', KillSlashes, test_str)
print(f"Result: {result}")

test_str2 = r'\\test'
print(f"Original: {test_str2}")
result2 = re.sub(r'(\\\\\\\\)|(\\\\)', KillSlashes, test_str2)
print(f"Result: {result2}")
