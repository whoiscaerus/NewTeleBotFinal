"""Final comprehensive fix for ALL User instantiations in test_social.py"""
import re

# Read file
with open('tests/test_social.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern: Find User( blocks that are missing email and password_hash
# These will have id= and telegram_user_id= but no email= or password_hash=

# Method: Find all User( blocks, check if they have email=, if not, add it

lines = content.split('\n')
result_lines = []
i = 0

while i < len(lines):
    line = lines[i]
    
    # Check if this line contains "= User("
    if '= User(' in line:
        # Start collecting the User block
        user_block = [line]
        i += 1
        
        # Collect until we find the closing paren
        paren_count = line.count('(') - line.count(')')
        while i < len(lines) and paren_count > 0:
            user_block.append(lines[i])
            paren_count += lines[i].count('(') - lines[i].count(')')
            i += 1
        
        # Now check if email= exists in this block
        block_text = '\n'.join(user_block)
        has_email = 'email=' in block_text
        
        if not has_email:
            # Need to add email and password_hash
            # Find the id= line and insert after it
            for j, block_line in enumerate(user_block):
                if 'id=' in block_line and '=' in block_line:
                    # Extract id value
                    id_match = re.search(r'id=f?"([^"]+)"', block_line)
                    if id_match:
                        id_value = id_match.group(1)
                        # Handle f-string formatting
                        if 'f"' in block_line:
                            # It's an f-string, keep format
                            pass
                        
                        # Insert email and password_hash after this line
                        indent = ' ' * (len(block_line) - len(block_line.lstrip()))
                        email_line = f'{indent}email=f"{id_value}@test.com",' if 'f"' in block_line else f'{indent}email="{id_value}@test.com",'
                        password_line = f'{indent}password_hash="hashed",'
                        
                        user_block.insert(j + 1, email_line)
                        user_block.insert(j + 2, password_line)
                        break
        
        # Add the modified block to results
        result_lines.extend(user_block)
    else:
        result_lines.append(line)
        i += 1

# Write back
with open('tests/test_social.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(result_lines))

print("Fixed all User instantiations that were missing email/password_hash")
