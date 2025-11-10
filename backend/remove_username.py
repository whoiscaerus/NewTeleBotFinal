"""Remove ALL remaining username= lines from test_social.py"""
import re

# Read file
with open('tests/test_social.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove any line containing "username=" (indented or not)
filtered_lines = [line for line in lines if 'username=' not in line]

# Write back
with open('tests/test_social.py', 'w', encoding='utf-8') as f:
    f.writelines(filtered_lines)

print(f"Removed {len(lines) - len(filtered_lines)} lines containing 'username='")
