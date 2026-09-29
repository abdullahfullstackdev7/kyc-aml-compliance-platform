import pytest

from backend.app.services.onboarding.state_machine import VALID_TRANSITIONS, InvalidTransitionError


def test_draft_can_only_go_to_submitted():
    assert VALID_TRANSITIONS["DRAFT"] == {"SUBMITTED"}


def test_screening_fans_out_to_four_outcomes():
    assert VALID_TRANSITIONS["SCREENING"] == {
        "AUTO_APPROVED",
        "PENDING_L1",
        "PENDING_L2",
        "SYSTEM_REJECTED",
    }


def test_pending_l1_can_escalate_or_clear_or_rfi():
    assert VALID_TRANSITIONS["PENDING_L1"] == {"CLEARED", "ESCALATED", "RFI_REQUESTED"}


def test_terminal_states_have_no_outgoing_transitions():
    for state in (
        "DOCS_FAILED",
        "SYSTEM_REJECTED",
        "AUTO_APPROVED",
        "CLEARED",
        "APPROVED",
        "REJECTED",
    ):
        assert VALID_TRANSITIONS[state] == set()


def test_transition_rejects_invalid_target():
    from unittest.mock import MagicMock

    from backend.app.services.onboarding.state_machine import transition

    application = MagicMock(state="DRAFT", id=1, tenant_id=1)
    session = MagicMock()
    with pytest.raises(InvalidTransitionError):
        transition(session, application, "APPROVED", actor_id=1, actor_role="customer")
