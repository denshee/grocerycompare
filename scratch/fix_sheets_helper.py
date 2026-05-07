import sys

with open('sheets_helper.py', 'r') as f:
    lines = f.readlines()

# Remove lines 169 to 201 (1-indexed, inclusive)
# In 0-indexed: lines[168:201]
new_lines = lines[:168] + lines[201:]

with open('sheets_helper.py', 'w') as f:
    f.writelines(new_lines)
