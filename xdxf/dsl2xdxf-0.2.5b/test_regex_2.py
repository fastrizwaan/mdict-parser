import re

def KillSlashes(matchobj):
    if matchobj.group(1): 
        print("Matched group 1 (double)")
        return '\\'
    else: 
        print("Matched group 2 (single)")
        return ''

test_str = r'\[C\]'
print(f"Original: {test_str}")
result = re.sub(r'(\\\\\\)|(\\)', KillSlashes, test_str)
print(f"Result: {result}")

test_str2 = r'\\test'
print(f"Original: {test_str2}")
result2 = re.sub(r'(\\\\\\)|(\\)', KillSlashes, test_str2)
print(f"Result: {result2}")
