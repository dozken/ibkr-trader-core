from enum import Enum
from typing import Dict, Set

class TradeState(str, Enum):
    """
    Trade life-cycle states.
    Ref: STATE_MACHINE.md Section 1.
    """
    IDLE = "IDLE"
    AI_ANALYSIS = "AI_ANALYSIS"
    SCREENING = "SCREENING"
    HALAL_CERTIFIED = "HALAL_CERTIFIED"
    PRE_ORDER = "PRE_ORDER"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"
    SETTLED = "SETTLED"
    REJECTED_COMPLIANCE = "REJECTED_COMPLIANCE"
    REJECTED_FUNDS = "REJECTED_FUNDS"
    IBKR_ERROR = "IBKR_ERROR"
    DRY_RUN = "DRY_RUN"

class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass

class TradeStateMachine:
    """
    Implements a strict trade state machine to prevent race conditions and non-compliant execution.
    Follows Track C rules (Trading & Infrastructure) per PARALLEL_WORKFLOW.md.
    Ref: AGENT.md - Ironclad Engineering & Fail-Closed logic.
    Ref: STATE_MACHINE.md - State definitions and guardrails.
    """
    
    def __init__(self, initial_state: TradeState = TradeState.IDLE):
        self._state = initial_state
        
        # Define allowed transitions (The Guardrails)
        # Ref: STATE_MACHINE.md Section 2
        self._allowed_transitions: Dict[TradeState, Set[TradeState]] = {
            TradeState.IDLE: {TradeState.AI_ANALYSIS},
            
            TradeState.AI_ANALYSIS: {TradeState.SCREENING, TradeState.IDLE},
            
            TradeState.SCREENING: {
                TradeState.HALAL_CERTIFIED, 
                TradeState.REJECTED_COMPLIANCE, 
                TradeState.IDLE
            },
            
            TradeState.HALAL_CERTIFIED: {TradeState.PRE_ORDER, TradeState.IDLE},
            
            TradeState.PRE_ORDER: {
                TradeState.SUBMITTED,
                TradeState.DRY_RUN,
                TradeState.REJECTED_FUNDS,
                TradeState.IDLE
            },

            TradeState.DRY_RUN: {TradeState.IDLE},
            
            TradeState.SUBMITTED: {TradeState.FILLED, TradeState.IBKR_ERROR},
            
            TradeState.FILLED: {
                TradeState.PENDING_SETTLEMENT, 
                TradeState.IBKR_ERROR
            },
            
            TradeState.PENDING_SETTLEMENT: {
                TradeState.SETTLED, 
                TradeState.IBKR_ERROR
            },
            
            TradeState.SETTLED: {TradeState.IDLE},
            
            # Failure states can reset to IDLE after intervention or safe shutdown
            TradeState.REJECTED_COMPLIANCE: {TradeState.IDLE},
            TradeState.REJECTED_FUNDS: {TradeState.IDLE},
            TradeState.IBKR_ERROR: {TradeState.IDLE},
        }

    @property
    def state(self) -> TradeState:
        """Returns the current state of the machine."""
        return self._state

    def transition_to(self, next_state: TradeState):
        """
        Attempts to transition to a new state.
        Validates against allowed transitions to ensure strict compliance.
        Ref: STATE_MACHINE.md Section 2 (Invalid Transitions).
        """
        allowed = self._allowed_transitions.get(self._state, set())
        
        # Add IBKR_ERROR as a global escape from non-idle/non-settled states if not already present
        if self._state not in {TradeState.IDLE, TradeState.SETTLED}:
            allowed.add(TradeState.IBKR_ERROR)
            
        if next_state not in allowed:
            raise InvalidTransitionError(
                f"Invalid transition from {self._state.name} to {next_state.name}. "
                "Must follow strict compliance workflow defined in STATE_MACHINE.md."
            )
            
        self._state = next_state
