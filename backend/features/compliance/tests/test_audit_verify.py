"""
Tests for GET /api/compliance/audit/verify and the underlying verify_audit_chain.

Covers:
- Empty table → valid (nothing to break)
- Single valid genesis entry → valid
- Two chained entries → valid
- Tampered hash → invalid
- Broken previous_hash pointer → invalid
- Endpoint returns correct shape
"""
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.models import Base, AuditLog
from backend.core.audit import verify_audit_chain, secure_log_entry


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _session(engine):
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# verify_audit_chain unit tests
# ---------------------------------------------------------------------------

class TestVerifyAuditChainUnit(unittest.TestCase):

    def test_empty_table_is_valid(self):
        db = _session(_make_engine())
        self.assertTrue(verify_audit_chain(db))

    def test_single_entry_valid(self):
        engine = _make_engine()
        db = _session(engine)
        entry = AuditLog(
            symbol="GENESIS", action="SYSTEM_INIT",
            shariah_status="N/A", metrics={},
        )
        secure_log_entry(db, entry)
        self.assertTrue(verify_audit_chain(db))

    def test_two_chained_entries_valid(self):
        engine = _make_engine()
        db = _session(engine)
        e1 = AuditLog(symbol="GENESIS", action="SYSTEM_INIT",
                      shariah_status="N/A", metrics={})
        secure_log_entry(db, e1)
        e2 = AuditLog(symbol="AAPL", action="BUY",
                      shariah_status="COMPLIANT", metrics={"debt": 0.1})
        secure_log_entry(db, e2)
        self.assertTrue(verify_audit_chain(db))

    def test_tampered_hash_detected(self):
        engine = _make_engine()
        db = _session(engine)
        entry = AuditLog(symbol="GENESIS", action="SYSTEM_INIT",
                         shariah_status="N/A", metrics={})
        secure_log_entry(db, entry)

        # Tamper the hash directly
        stored = db.query(AuditLog).first()
        stored.hash = "deadbeef" * 8
        db.commit()

        self.assertFalse(verify_audit_chain(db))

    def test_broken_previous_hash_pointer_detected(self):
        engine = _make_engine()
        db = _session(engine)
        e1 = AuditLog(symbol="GENESIS", action="SYSTEM_INIT",
                      shariah_status="N/A", metrics={})
        secure_log_entry(db, e1)
        e2 = AuditLog(symbol="AAPL", action="BUY",
                      shariah_status="COMPLIANT", metrics={})
        secure_log_entry(db, e2)

        # Break the chain pointer on the second entry
        second = db.query(AuditLog).order_by(AuditLog.id.asc()).all()[1]
        second.previous_hash = "wronghash"
        db.commit()

        self.assertFalse(verify_audit_chain(db))


# ---------------------------------------------------------------------------
# /api/compliance/audit/verify endpoint test
# ---------------------------------------------------------------------------

class TestAuditVerifyEndpoint(unittest.TestCase):

    def _call(self, valid: bool, count: int):
        from backend.features.compliance.router import verify_audit_integrity
        mock_db = MagicMock()
        mock_db.query.return_value.scalar.return_value = count
        with patch("backend.features.compliance.router.verify_audit_chain", return_value=valid):
            return verify_audit_integrity(db=mock_db)

    def test_valid_chain_response(self):
        result = self._call(valid=True, count=42)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 42)
        self.assertIn("intact", result["message"])

    def test_invalid_chain_response(self):
        result = self._call(valid=False, count=10)
        self.assertFalse(result["valid"])
        self.assertIn("TAMPER", result["message"])

    def test_empty_db_valid(self):
        result = self._call(valid=True, count=0)
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 0)


if __name__ == "__main__":
    unittest.main()
