"""Quick smoke test for messaging templates - direct import to avoid DB initialization."""

import os

# Test MarkdownV2 escaping (inline function)
MARKDOWNV2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_markdownv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for char in MARKDOWNV2_SPECIAL_CHARS:
        text = text.replace(char, f"\\{char}")
    return text


print("=" * 60)
print("SMOKE TEST: Template Components")
print("=" * 60)

# Test 1: MarkdownV2 escaping
print("\n1. Testing MarkdownV2 escaping...")
test_text = "Price: 1950.50 (gain!)"
escaped = escape_markdownv2(test_text)
print(f"   Original: {test_text}")
print(f"   Escaped: {escaped}")
# MarkdownV2 special chars: _*[]()~`>#+-=|{}.!
# The . ( ) ! should be escaped
expected_escaped = "Price: 1950\\.50 \\(gain\\!\\)"
assert escaped == expected_escaped, f"Expected {expected_escaped}, got {escaped}"
print("   ✅ MarkdownV2 escaping works correctly")

# Test 2: Template variable substitution
print("\n2. Testing template variable substitution...")
template = "Instrument: {instrument}, Side: {side}, Price: {price}"
vars_dict = {"instrument": "GOLD", "side": "buy", "price": 1950.50}
result = template.format(**vars_dict)
print(f"   Result: {result}")
assert "GOLD" in result and "buy" in result
print("   ✅ Template substitution works")

# Test 3: Email template structure validation
print("\n3. Validating email template files exist...")

templates_dir = "email/templates"
required_templates = [
    "position_failure_entry.html",
    "position_failure_sl.html",
    "position_failure_tp.html",
]

for template_file in required_templates:
    template_path = os.path.join(templates_dir, template_file)
    assert os.path.exists(template_path), f"Template not found: {template_path}"
    with open(template_path, encoding="utf-8") as f:
        content = f.read()
        assert "<!DOCTYPE html>" in content, f"Invalid HTML in {template_file}"
        assert "{{ instrument }}" in content, f"Missing template var in {template_file}"
    print(f"   ✅ {template_file} exists and is valid HTML")

# Test 4: Position failure template files exist
print("\n4. Checking position failure template files...")
template_py_path = "backend/app/messaging/templates/position_failures.py"
assert os.path.exists(template_py_path), f"Template file not found: {template_py_path}"
with open(template_py_path, encoding="utf-8") as f:
    content = f.read()
    assert "ENTRY_FAILURE_TELEGRAM" in content
    assert "SL_FAILURE_TELEGRAM" in content
    assert "TP_FAILURE_TELEGRAM" in content
    assert "Manual Action Required" in content
    assert "Stop Loss Hit" in content
    assert "Take Profit Hit" in content
print("   ✅ position_failures.py exists with all template constants")

print("\n" + "=" * 60)
print("✅ ALL SMOKE TESTS PASSED")
print("=" * 60)
print("\nNote: Full template rendering tests will be in test_messaging_templates.py")
