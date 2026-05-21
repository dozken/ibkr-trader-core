import logging
from ibkr_core.core.database import init_db, SessionLocal
from ibkr_core.core.models import AuditLog

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_system(db_session=None):
    """
    Initializes the database and seeds the Genesis audit log.
    
    Track C: Trading & Infrastructure implementation.
    Ref: AUDIT_LOG.md Section 2 - Immutable Ledger & Verification.
    Cite: AGENT.md - Ironclad Engineering & Transparency.
    """
    logger.info("Initializing database tables...")
    init_db()
    
    session = db_session if db_session else SessionLocal()
    try:
        # Check if Genesis log already exists
        genesis = session.query(AuditLog).filter(AuditLog.symbol == "GENESIS").first()
        
        if not genesis:
            logger.info("Creating Genesis Audit Log for ledger integrity...")
            from ibkr_core.core.audit import secure_log_entry
            genesis_log = AuditLog(
                symbol="GENESIS",
                action="SYSTEM_INIT",
                shariah_status="VERIFIED",
                data_source="INTERNAL",
                metrics={
                    "version": "1.0.0",
                    "status": "ledger_initialized",
                    "checksum_verification": "enabled"
                },
                business_activity="System Infrastructure",
                ibkr_order_id=0
            )
            secure_log_entry(session, genesis_log)
            logger.info("Genesis Audit Log created successfully.")
        else:
            logger.info("Genesis Audit Log already exists. Skipping.")
            
    except Exception as e:
        logger.error(f"Error during system initialization: {e}")
        session.rollback()
        raise
    finally:
        if not db_session:
            session.close()

if __name__ == "__main__":
    initialize_system()
