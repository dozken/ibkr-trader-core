import hashlib
import json
import logging
from sqlalchemy.orm import Session
from backend.core.models import AuditLog

logger = logging.getLogger(__name__)

def calculate_audit_hash(log_entry: AuditLog, previous_hash: str = "GENESIS") -> str:
    """
    Calculates a SHA-256 hash for an audit log entry.
    Chains entries together via the previous_hash.
    """
    # Serialize entry data (excluding internal DB fields like id and the hash itself)
    ts = log_entry.timestamp
    if ts and ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)  # normalize: SQLite strips tz on round-trip
    content = {
        "timestamp": ts.isoformat() if ts else "",
        "symbol": log_entry.symbol,
        "action": log_entry.action,
        "shariah_status": log_entry.shariah_status,
        "metrics": log_entry.metrics,
        "business_activity": log_entry.business_activity,
        "ibkr_order_id": "None",  # excluded from hash — set post-execution, not part of compliance decision
        "previous_hash": previous_hash
    }
    
    encoded = json.dumps(content, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()

def secure_log_entry(db: Session, log_entry: AuditLog) -> AuditLog:
    """
    Retrieves the previous entry, calculates the hash, and saves the secured entry.
    """
    last_entry = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    raw = getattr(last_entry, "hash", None) if last_entry else None
    prev_hash = raw if isinstance(raw, str) else "GENESIS"

    log_entry.previous_hash = prev_hash
    db.add(log_entry)
    db.flush()  # triggers INSERT so SQLAlchemy populates timestamp default
    log_entry.hash = calculate_audit_hash(log_entry, prev_hash)
    db.commit()
    db.refresh(log_entry)
    return log_entry

def verify_audit_chain(db: Session) -> bool:
    """
    Validates the entire cryptographic chain of the AuditLog table.
    Returns True if valid, False if any entry is tampered with.
    """
    logs = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    
    expected_prev_hash = "GENESIS"
    
    for i, log in enumerate(logs):
        if log.symbol == "GENESIS" and i == 0:
             # Special case for Genesis entry if it was created without a hash
             if not log.hash:
                 logger.warning("Genesis log entry lacks a hash. Skipping verification for first entry.")
                 expected_prev_hash = "GENESIS" # Update if genesis has a known hash logic
                 continue
        
        # Recalculate hash
        calculated = calculate_audit_hash(log, log.previous_hash)
        
        if calculated != log.hash:
            logger.error(f"TAMPER DETECTED: AuditLog ID {log.id} has invalid hash.")
            return False
            
        if log.previous_hash != expected_prev_hash:
            logger.error(f"CHAIN BREAK: AuditLog ID {log.id} previous_hash mismatch.")
            return False
            
        expected_prev_hash = log.hash
        
    return True
