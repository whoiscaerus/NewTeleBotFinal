#!/usr/bin/env python3
import hashlib
import hmac
import time

secret = 'whsec_test_secret_key'
timestamp = str(int(time.time()))
body = '{"event": "charge.succeeded"}'

signed_content = f'{timestamp}.{body}'
print(f'Signed content: {signed_content}')

expected_signature = hmac.new(
    secret.encode(),
    signed_content.encode(),
    hashlib.sha256,
).hexdigest()

print(f'Expected signature: {expected_signature}')
print(f'Timestamp: {timestamp}')

# Verify
sig_header = f't={timestamp},v1={expected_signature}'
print(f'Sig header: {sig_header}')

# Parse
timestamp_parsed, signature_parsed = None, None
for item in sig_header.split(','):
    print(f'Parsing item: "{item}"')
    if item.startswith('t='):
        timestamp_parsed = item[2:]
        print(f'  -> timestamp = {timestamp_parsed}')
    elif item.startswith('v1='):
        signature_parsed = item[3:]  # Should be [3:], not [4:]
        print(f'  -> signature = {signature_parsed}')

print(f'Parsed timestamp: {timestamp_parsed}')
print(f'Parsed signature: {signature_parsed}')

# Recompute
signed_content_2 = f'{timestamp_parsed}.{body}'
expected_sig_2 = hmac.new(
    secret.encode('utf-8'),
    signed_content_2.encode(),
    hashlib.sha256,
).hexdigest()

print(f'Recomputed signature: {expected_sig_2}')
print(f'Match: {hmac.compare_digest(expected_sig_2, signature_parsed)}')
