# Copy Style Guide

**Caerus Trading - Content & Localization Guidelines**

Version: 1.0
Last Updated: November 8, 2025

---

## Table of Contents

1. [Introduction](#introduction)
2. [Brand Voice & Tone](#brand-voice--tone)
3. [Writing Guidelines](#writing-guidelines)
4. [Localization Principles](#localization-principles)
5. [Copy Types](#copy-types)
6. [A/B Testing Best Practices](#ab-testing-best-practices)
7. [Approval Workflow](#approval-workflow)

---

## Introduction

This style guide ensures consistency across all Caerus Trading copy - from product UI to marketing campaigns to legal disclaimers. All contributors (writers, translators, product managers) should follow these guidelines.

### Goals

- **Clarity**: Users understand what to do
- **Trust**: Professional, accurate, transparent
- **Accessibility**: Simple language, no jargon
- **Localization**: Natural in every language

---

## Brand Voice & Tone

### Voice (Consistent Across All Content)

**Professional + Approachable**

- We're experts, but not condescending
- We explain complex trading concepts simply
- We're honest about risks (no hype)

**Core Attributes:**
- **Confident**: We know trading, but...
- **Humble**: We respect the user's expertise
- **Transparent**: We disclose risks and limitations
- **Supportive**: We help users succeed

### Tone (Varies by Context)

| Context | Tone | Example |
|---------|------|---------|
| **Product UI** | Direct, action-oriented | "Approve Signal", not "Would you like to approve this signal?" |
| **Marketing** | Encouraging, benefit-focused | "Take control of your trading with AI-powered signals" |
| **Legal** | Formal, precise | "Trading involves risk of substantial loss. Past performance..." |
| **Errors** | Calm, helpful | "We couldn't process your request. Please try again." |
| **Success** | Positive, brief | "Signal approved successfully" |

---

## Writing Guidelines

### General Rules

1. **Be Concise**
   - ✅ "Approve Signal"
   - ❌ "Click here to approve this trading signal"

2. **Use Active Voice**
   - ✅ "Configure your devices"
   - ❌ "Devices can be configured"

3. **Write in Present Tense**
   - ✅ "Your plan renews on..."
   - ❌ "Your plan will be renewed on..."

4. **Avoid Jargon**
   - ✅ "Stop Loss" (industry standard)
   - ❌ "Risk mitigation trigger point"
   - Exception: Technical terms when necessary (MT5, API, etc.)

5. **Be Specific**
   - ✅ "You have 72 hours to cancel"
   - ❌ "You have a few days to cancel"

6. **Use Numbers, Not Words**
   - ✅ "3 pending signals"
   - ❌ "Three pending signals"

### Buttons & CTAs

**Format**: Verb + Noun (when possible)

- ✅ "Create Alert"
- ✅ "Export Data"
- ✅ "Upgrade Plan"
- ❌ "Click to Create"
- ❌ "Export"

**Primary Actions**: Bold, direct
- "Approve", "Confirm", "Save Changes"

**Secondary Actions**: Neutral
- "Cancel", "Back", "Skip"

**Destructive Actions**: Clear consequences
- "Delete Account" (not "Remove")
- "Revoke Device" (not "Disconnect")

### Error Messages

**Structure**: Problem + Solution

- ✅ "Network error. Please check your connection."
- ❌ "Error 500"

**Tone**: Calm, helpful (never blame user)

- ✅ "Please check your input and try again."
- ❌ "You entered invalid data."

### Success Messages

**Structure**: Action Completed + (Optional Next Step)

- ✅ "Signal approved successfully"
- ✅ "Device added. Copy the secret now—it won't be shown again."
- ❌ "Success!"

---

## Localization Principles

### Translation Guidelines

1. **Translate Meaning, Not Words**
   - Idiomatic expressions should be localized
   - Cultural references may need adaptation

2. **Preserve Tone**
   - Professional + approachable tone must carry through
   - Avoid overly formal translations (e.g., Spanish "usted" vs. "tú")

3. **Technical Terms**
   - Keep industry-standard terms in English when appropriate
   - "Stop Loss", "Take Profit", "Drawdown" → universal
   - Add localized explanations when needed

4. **Formatting**
   - Dates: Use locale format (DD/MM/YYYY for UK, MM/DD/YYYY for US)
   - Currency: Always show symbol (£, €, $)
   - Numbers: Respect locale decimal separators

5. **String Length**
   - Allow 30-50% expansion for German, Finnish
   - Some languages (Spanish) are ~20% longer than English
   - Test UI with longest translations

### Supported Locales

**Current:**
- `en`: English (UK) - Default
- `es`: Spanish (Spain + LATAM)

**Planned:**
- `fr`: French
- `de`: German
- `pt`: Portuguese

### Locale-Specific Notes

**Spanish (`es`):**
- Use "tú" (informal) for product UI
- Use "usted" (formal) for legal/compliance
- LATAM vs. Spain: Prefer neutral Spanish (avoid regionalisms)

---

## Copy Types

### 1. Product Copy

**Purpose**: UI labels, buttons, tooltips, navigation

**Requirements:**
- Maximum brevity
- Action-oriented
- Sentence case (not title case)

**Examples:**
```json
{
  "approvals.approve": "Approve",
  "devices.addDevice": "Add Device",
  "billing.upgrade": "Upgrade Plan"
}
```

### 2. Legal Copy

**Purpose**: Terms, disclaimers, policies

**Requirements:**
- Formal tone
- Precise language
- Compliance-reviewed
- Version-tracked

**Examples:**
```json
{
  "legal.riskDisclaimer": "Trading involves risk of substantial loss. Past performance does not guarantee future results.",
  "legal.copyTradingConsent": "You acknowledge that copy trading executes trades automatically without manual approval."
}
```

### 3. Marketing Copy

**Purpose**: Landing pages, CTAs, campaigns, emails

**Requirements:**
- Benefit-focused
- Encouraging tone
- Clear value proposition
- A/B testable

**Examples:**
```json
{
  "marketing.heroCta": "Start Trading Smarter",
  "marketing.emailSubject": "Your First Signal is Ready",
  "marketing.upgradeNudge": "Unlock advanced analytics with Pro"
}
```

### 4. Notification Copy

**Purpose**: Alerts, system messages, push notifications

**Requirements:**
- Urgent tone (when appropriate)
- Actionable
- Brief (push: max 50 chars)

**Examples:**
```json
{
  "notification.signalReady": "New signal ready for review",
  "notification.priceAlert": "GOLD crossed above $1,950",
  "notification.billingFailed": "Payment failed. Update your card."
}
```

### 5. Error Messages

**Purpose**: Validation errors, API failures, exceptions

**Requirements:**
- Problem + solution
- Calm tone
- No technical jargon

**Examples:**
```json
{
  "error.networkError": "Network error. Please check your connection.",
  "error.authError": "Authentication failed. Please log in again.",
  "error.validationError": "Please check your input and try again."
}
```

---

## A/B Testing Best Practices

### When to A/B Test Copy

✅ **Good Candidates:**
- CTA buttons (conversion-critical)
- Hero headlines (first impression)
- Upgrade prompts (revenue impact)
- Error recovery flows (user friction)

❌ **Poor Candidates:**
- Legal disclaimers (must be precise)
- Navigation labels (consistency matters)
- Error messages (clarity > optimization)

### Test Structure

1. **Control Variant**: Current/default copy
2. **Variant A/B**: Alternative phrasing
3. **Hypothesis**: "Variant A will increase conversions because..."

### Metrics

- **Impressions**: How many times shown
- **Conversions**: Desired action taken
- **Conversion Rate**: conversions / impressions

### Sample Size

- Minimum 100 conversions per variant
- Run test for at least 7 days (account for weekly patterns)
- Statistical significance: p < 0.05

### Examples

**CTA Test:**
- Control: "Upgrade Plan"
- Variant A: "Unlock Pro Features"
- Variant B: "Get Advanced Analytics"
- Hypothesis: Benefit-focused copy (Variant A/B) increases upgrade clicks

**Hero Test:**
- Control: "Professional Trading Signals"
- Variant A: "Trade Smarter with AI Signals"
- Variant B: "Never Miss a Trade"
- Hypothesis: Variant A emphasizes intelligence; Variant B emphasizes FOMO

---

## Approval Workflow

### Roles

1. **Writer**: Creates copy, submits for review
2. **Editor**: Reviews for style, clarity, accuracy
3. **Translator**: Localizes approved English copy
4. **Legal** (if applicable): Reviews legal/compliance copy
5. **Product Manager**: Final approval, publishes

### Status Lifecycle

```
draft → review → approved → published → archived
```

- **draft**: Being authored
- **review**: Pending editor/legal approval
- **approved**: Ready for use (not yet live)
- **published**: Live in production
- **archived**: No longer active (replaced/deprecated)

### Review Checklist

**Editor:**
- [ ] Follows style guide (voice, tone, format)
- [ ] Grammar and spelling correct
- [ ] No jargon or complex language
- [ ] Length appropriate for UI space
- [ ] Consistent with existing copy

**Translator:**
- [ ] Meaning preserved (not literal translation)
- [ ] Tone appropriate for locale
- [ ] Technical terms handled correctly
- [ ] Length fits UI constraints
- [ ] Reviewed by native speaker

**Legal (if applicable):**
- [ ] Disclaimers accurate and complete
- [ ] Regulatory requirements met
- [ ] No misleading claims
- [ ] Version tracked for audit

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-08 | Initial style guide created for PR-069 |

---

## Questions?

Contact the content team or file an issue in the copy registry.

**Copy Registry**: `/api/v1/copy`
**Documentation**: `/docs/copy`
