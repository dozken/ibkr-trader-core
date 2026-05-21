import unittest
from ibkr_core.core.state import TradeState, TradeStateMachine, InvalidTransitionError

class TestTradeStateMachine(unittest.TestCase):
    def test_initial_state(self):
        machine = TradeStateMachine()
        self.assertEqual(machine.state, TradeState.IDLE)

    def test_happy_path(self):
        machine = TradeStateMachine()
        
        # IDLE -> AI_ANALYSIS
        machine.transition_to(TradeState.AI_ANALYSIS)
        self.assertEqual(machine.state, TradeState.AI_ANALYSIS)
        
        # AI_ANALYSIS -> SCREENING
        machine.transition_to(TradeState.SCREENING)
        self.assertEqual(machine.state, TradeState.SCREENING)
        
        # SCREENING -> HALAL_CERTIFIED
        machine.transition_to(TradeState.HALAL_CERTIFIED)
        self.assertEqual(machine.state, TradeState.HALAL_CERTIFIED)
        
        # HALAL_CERTIFIED -> PRE_ORDER
        machine.transition_to(TradeState.PRE_ORDER)
        self.assertEqual(machine.state, TradeState.PRE_ORDER)
        
        # PRE_ORDER -> SUBMITTED
        machine.transition_to(TradeState.SUBMITTED)
        self.assertEqual(machine.state, TradeState.SUBMITTED)
        
        # SUBMITTED -> FILLED
        machine.transition_to(TradeState.FILLED)
        self.assertEqual(machine.state, TradeState.FILLED)
        
        # FILLED -> PENDING_SETTLEMENT
        machine.transition_to(TradeState.PENDING_SETTLEMENT)
        self.assertEqual(machine.state, TradeState.PENDING_SETTLEMENT)
        
        # PENDING_SETTLEMENT -> SETTLED
        machine.transition_to(TradeState.SETTLED)
        self.assertEqual(machine.state, TradeState.SETTLED)
        
        # SETTLED -> IDLE
        machine.transition_to(TradeState.IDLE)
        self.assertEqual(machine.state, TradeState.IDLE)

    def test_blocked_idle_to_submitted(self):
        machine = TradeStateMachine()
        with self.assertRaises(InvalidTransitionError):
            machine.transition_to(TradeState.SUBMITTED)

    def test_blocked_pending_settlement_to_idle(self):
        machine = TradeStateMachine()
        # Reach PENDING_SETTLEMENT
        states = [
            TradeState.AI_ANALYSIS, TradeState.SCREENING, TradeState.HALAL_CERTIFIED,
            TradeState.PRE_ORDER, TradeState.SUBMITTED, TradeState.FILLED,
            TradeState.PENDING_SETTLEMENT
        ]
        for s in states:
            machine.transition_to(s)
        
        with self.assertRaises(InvalidTransitionError):
            machine.transition_to(TradeState.IDLE)

    def test_blocked_filled_to_screening(self):
        machine = TradeStateMachine()
        # Reach FILLED
        states = [
            TradeState.AI_ANALYSIS, TradeState.SCREENING, TradeState.HALAL_CERTIFIED,
            TradeState.PRE_ORDER, TradeState.SUBMITTED, TradeState.FILLED
        ]
        for s in states:
            machine.transition_to(s)
        
        with self.assertRaises(InvalidTransitionError):
            machine.transition_to(TradeState.SCREENING)

    def test_failure_states(self):
        # From SCREENING to REJECTED_COMPLIANCE
        machine = TradeStateMachine()
        machine.transition_to(TradeState.AI_ANALYSIS)
        machine.transition_to(TradeState.SCREENING)
        machine.transition_to(TradeState.REJECTED_COMPLIANCE)
        self.assertEqual(machine.state, TradeState.REJECTED_COMPLIANCE)
        
        # From PRE_ORDER to REJECTED_FUNDS
        machine = TradeStateMachine()
        machine.transition_to(TradeState.AI_ANALYSIS)
        machine.transition_to(TradeState.SCREENING)
        machine.transition_to(TradeState.HALAL_CERTIFIED)
        machine.transition_to(TradeState.PRE_ORDER)
        machine.transition_to(TradeState.REJECTED_FUNDS)
        self.assertEqual(machine.state, TradeState.REJECTED_FUNDS)

        # From any state to IBKR_ERROR (e.g. SUBMITTED)
        machine = TradeStateMachine()
        machine.transition_to(TradeState.AI_ANALYSIS)
        machine.transition_to(TradeState.SCREENING)
        machine.transition_to(TradeState.HALAL_CERTIFIED)
        machine.transition_to(TradeState.PRE_ORDER)
        machine.transition_to(TradeState.SUBMITTED)
        machine.transition_to(TradeState.IBKR_ERROR)
        self.assertEqual(machine.state, TradeState.IBKR_ERROR)

if __name__ == '__main__':
    unittest.main()
