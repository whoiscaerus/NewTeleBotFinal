"""Fix malformed User instantiations in test_social.py"""
import re

# Read file
with open('tests/test_social.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix backtick-n literals to actual newlines
content = content.replace('`n        ', '\n        ')

# Write back
with open('tests/test_social.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all backtick-n patterns")
