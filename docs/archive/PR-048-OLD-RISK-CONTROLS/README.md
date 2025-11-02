⚠️ ARCHIVED - OLD PR-048 RISK CONTROLS DOCUMENTATION

This directory contains the original PR-048 documentation for "Risk Controls & Guardrails"
which was superceded by the new PR-048 specification for "Auto-Trace to Third-Party Trackers".

The Risk Controls feature itself remains implemented and in use in the codebase:
  ✅ /backend/app/risk/ (models, service, routes)
  ✅ /backend/app/tasks/risk_tasks.py
  ✅ /backend/tests/test_pr_048_risk_controls.py
  ✅ Database migration: 048_add_risk_tables.py

However, the Master PR document (Final_Master_Prs.md) defines PR-048 as "Auto-Trace to
Third-Party Trackers (Post-Close)" going forward. This documentation is retained for
reference but is no longer the active PR-048 specification.

For the current PR-048 (Auto-Trace) implementation, see:
  → /docs/prs/PR-048-IMPLEMENTATION-PLAN.md
  → /docs/prs/PR-048-ACCEPTANCE-CRITERIA.md
  → /docs/prs/PR-048-IMPLEMENTATION-COMPLETE.md
  → /docs/prs/PR-048-BUSINESS-IMPACT.md

Archived on: November 1, 2025
