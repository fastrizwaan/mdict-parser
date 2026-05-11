import re

# Match one backslash
print(f"One backslash test: {re.findall(r'\\', r'\\')}")
# Match two backslashes
print(f"Two backslashes test: {re.findall(r'\\\\', r'\\\\')}")
