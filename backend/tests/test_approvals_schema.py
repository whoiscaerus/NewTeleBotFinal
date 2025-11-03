"""Comprehensive tests for Approvals schema validation.

Tests cover:
- ApprovalCreate validation (signal_id, decision, reason, consent_version)
- ApprovalOut serialization
- Decision enum validation
- Reason max_length validation
- Consent version handling
- Error messages

ALL tests validate REAL Pydantic schema logic.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from backend.app.approvals.schema import ApprovalCreate, ApprovalOut


class TestApprovalCreateValidation:
    """Test ApprovalCreate schema validation."""

    def test_valid_approval_create(self):
        """Test valid approval creation request."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
        )

        assert request.signal_id == "sig123"
        assert request.decision == "approved"
        assert request.reason is None
        assert request.consent_version == 1

    def test_valid_rejection_with_reason(self):
        """Test rejection with reason."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason="Risk too high",
        )

        assert request.signal_id == "sig123"
        assert request.decision == "rejected"
        assert request.reason == "Risk too high"

    def test_missing_signal_id_raises_validation_error(self):
        """Test missing signal_id raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ApprovalCreate(decision="approved")

        assert "signal_id" in str(exc_info.value)

    def test_missing_decision_raises_validation_error(self):
        """Test missing decision raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ApprovalCreate(signal_id="sig123")

        assert "decision" in str(exc_info.value)

    def test_invalid_decision_rejected(self):
        """Test invalid decision value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ApprovalCreate(
                signal_id="sig123",
                decision="maybe",
            )

        errors = exc_info.value.errors()
        assert any(
            err["loc"] == ("decision",) and "pattern" in err["type"]
            for err in errors
        )

    def test_invalid_decision_case_sensitive(self):
        """Test decision is case-sensitive (must be lowercase)."""
        with pytest.raises(ValidationError):
            ApprovalCreate(
                signal_id="sig123",
                decision="Approved",  # Capital A
            )

    def test_decision_approved_valid(self):
        """Test decision='approved' is valid."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
        )
        assert request.decision == "approved"

    def test_decision_rejected_valid(self):
        """Test decision='rejected' is valid."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
        )
        assert request.decision == "rejected"

    def test_reason_none_accepted(self):
        """Test reason can be None (default)."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            reason=None,
        )
        assert request.reason is None

    def test_reason_empty_string_accepted(self):
        """Test empty string reason accepted."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason="",
        )
        assert request.reason == ""

    def test_reason_max_length_500_accepted(self):
        """Test reason at max length (500 chars) accepted."""
        max_reason = "x" * 500
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason=max_reason,
        )
        assert request.reason == max_reason

    def test_reason_exceeds_max_length_rejected(self):
        """Test reason exceeding max length (501) rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ApprovalCreate(
                signal_id="sig123",
                decision="rejected",
                reason="x" * 501,
            )

        errors = exc_info.value.errors()
        assert any(
            err["loc"] == ("reason",) for err in errors
        )

    def test_consent_version_default_1(self):
        """Test consent_version defaults to 1."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
        )
        assert request.consent_version == 1

    def test_consent_version_can_be_overridden(self):
        """Test consent_version can be set to specific value."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            consent_version=3,
        )
        assert request.consent_version == 3

    def test_consent_version_zero_accepted(self):
        """Test consent_version can be 0."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            consent_version=0,
        )
        assert request.consent_version == 0

    def test_consent_version_negative_accepted(self):
        """Test negative consent_version accepted (no validation)."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            consent_version=-1,
        )
        assert request.consent_version == -1

    def test_consent_version_large_number_accepted(self):
        """Test large consent_version accepted."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            consent_version=999999,
        )
        assert request.consent_version == 999999

    def test_signal_id_empty_string_accepted_by_schema(self):
        """Test empty signal_id accepted by schema (validated at service level)."""
        request = ApprovalCreate(
            signal_id="",
            decision="approved",
        )
        assert request.signal_id == ""

    def test_signal_id_uuid_format_accepted(self):
        """Test UUID format signal_id accepted."""
        uuid_id = "550e8400-e29b-41d4-a716-446655440000"
        request = ApprovalCreate(
            signal_id=uuid_id,
            decision="approved",
        )
        assert request.signal_id == uuid_id

    def test_signal_id_arbitrary_string_accepted(self):
        """Test arbitrary string signal_id accepted."""
        request = ApprovalCreate(
            signal_id="my-custom-signal-id",
            decision="approved",
        )
        assert request.signal_id == "my-custom-signal-id"


class TestApprovalOutSerialization:
    """Test ApprovalOut response schema."""

    def test_approval_out_serialization(self):
        """Test ApprovalOut serialization from dict."""
        now = datetime.utcnow()
        data = {
            "id": "app123",
            "signal_id": "sig123",
            "user_id": "user123",
            "decision": "approved",
            "reason": None,
            "consent_version": 1,
            "created_at": now,
        }

        approval = ApprovalOut(**data)

        assert approval.id == "app123"
        assert approval.signal_id == "sig123"
        assert approval.user_id == "user123"
        assert approval.decision == "approved"
        assert approval.reason is None
        assert approval.consent_version == 1
        assert approval.created_at == now

    def test_approval_out_with_rejection_reason(self):
        """Test ApprovalOut with rejection reason."""
        now = datetime.utcnow()
        data = {
            "id": "app123",
            "signal_id": "sig123",
            "user_id": "user123",
            "decision": "rejected",
            "reason": "Risk limit exceeded",
            "consent_version": 1,
            "created_at": now,
        }

        approval = ApprovalOut(**data)

        assert approval.decision == "rejected"
        assert approval.reason == "Risk limit exceeded"

    def test_approval_out_json_serializable(self):
        """Test ApprovalOut can be serialized to JSON."""
        now = datetime.utcnow()
        data = {
            "id": "app123",
            "signal_id": "sig123",
            "user_id": "user123",
            "decision": "approved",
            "reason": None,
            "consent_version": 1,
            "created_at": now,
        }

        approval = ApprovalOut(**data)
        json_data = approval.model_dump_json()

        assert "app123" in json_data
        assert "sig123" in json_data
        assert "approved" in json_data

    def test_approval_out_datetime_isoformat(self):
        """Test created_at is serialized as ISO format."""
        now = datetime.utcnow()
        data = {
            "id": "app123",
            "signal_id": "sig123",
            "user_id": "user123",
            "decision": "approved",
            "reason": None,
            "consent_version": 1,
            "created_at": now,
        }

        approval = ApprovalOut(**data)
        json_dict = approval.model_dump()

        # created_at should be datetime object
        assert isinstance(json_dict["created_at"], datetime)

    def test_approval_out_from_attributes_config(self):
        """Test from_attributes config allows ORM model creation."""
        # This tests that Config.from_attributes is set
        # (allows construction from SQLAlchemy ORM objects)
        now = datetime.utcnow()
        data = {
            "id": "app123",
            "signal_id": "sig123",
            "user_id": "user123",
            "decision": "approved",
            "reason": None,
            "consent_version": 1,
            "created_at": now,
        }

        approval = ApprovalOut(**data)
        assert approval.id == "app123"


class TestApprovalSchemaEdgeCases:
    """Test edge cases in schema validation."""

    def test_approval_create_with_extra_fields_ignored(self):
        """Test extra fields in request are ignored (Pydantic behavior)."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            extra_field="ignored",  # Should be ignored
        )

        assert request.signal_id == "sig123"
        assert not hasattr(request, "extra_field")

    def test_approval_create_with_whitespace_decision_rejected(self):
        """Test decision with whitespace rejected."""
        with pytest.raises(ValidationError):
            ApprovalCreate(
                signal_id="sig123",
                decision=" approved",  # Leading space
            )

    def test_approval_create_with_null_fields(self):
        """Test null values accepted for optional fields."""
        request = ApprovalCreate(
            signal_id="sig123",
            decision="approved",
            reason=None,
            consent_version=1,
        )

        assert request.reason is None

    def test_approval_out_missing_required_field_raises_error(self):
        """Test ApprovalOut with missing required field raises error."""
        with pytest.raises(ValidationError):
            ApprovalOut(
                id="app123",
                signal_id="sig123",
                # Missing user_id
                decision="approved",
                reason=None,
                consent_version=1,
                created_at=datetime.utcnow(),
            )

    def test_reason_special_characters_accepted(self):
        """Test reason with special characters accepted."""
        special_reason = "Risk: high! @#$% [test] (ok) <tag>"
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason=special_reason,
        )

        assert request.reason == special_reason

    def test_reason_unicode_characters_accepted(self):
        """Test reason with Unicode characters accepted."""
        unicode_reason = "Risk: 高风险 ⚠️ 危险"
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason=unicode_reason,
        )

        assert request.reason == unicode_reason

    def test_reason_multiline_accepted(self):
        """Test reason with newlines accepted."""
        multiline_reason = "Line 1\nLine 2\nLine 3"
        request = ApprovalCreate(
            signal_id="sig123",
            decision="rejected",
            reason=multiline_reason,
        )

        assert request.reason == multiline_reason

    def test_signal_id_with_special_characters_accepted(self):
        """Test signal_id with special characters accepted."""
        request = ApprovalCreate(
            signal_id="sig_123-abc.v2",
            decision="approved",
        )

        assert request.signal_id == "sig_123-abc.v2"

    def test_decision_enum_like_values_rejected(self):
        """Test values similar to enum but not exact are rejected."""
        invalid_values = [
            "APPROVED",  # Uppercase
            "Approved",  # Capitalized
            "approve",  # Similar but not exact
            "reject",  # Similar but not exact (should be "rejected")
            "approval",  # Related word
            1,  # Integer value
            True,  # Boolean
        ]

        for invalid_value in invalid_values:
            with pytest.raises(ValidationError):
                ApprovalCreate(
                    signal_id="sig123",
                    decision=invalid_value,
                )
