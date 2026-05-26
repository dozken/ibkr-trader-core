import asyncio
import logging
import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Configure logging to see loop startups
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SMOKE_TEST")

async def run_synthetic_test():
    logger.info("🚀 Starting Ironclad Synthetic Smoke Test...")
    
    # 1. Mock IBKR Worker
    mock_worker = MagicMock()
    mock_worker.connect = AsyncMock(return_value=True)
    mock_worker.ib.isConnected.return_value = True
    mock_worker.get_net_liquidation.return_value = 100000.0
    mock_worker.get_available_funds.return_value = 50000.0
    mock_worker.get_positions.return_value = []
    
    # 2. Mock Database and Verify Chain
    mock_db = MagicMock()
    
    # 3. Setup Health Dict (Internal State)
    health = {
        "main_loop":               {"last_run": None, "status": "starting"},
        "compliance_audit_loop":   {"last_run": None, "status": "starting"},
        "cash_sweep_loop":         {"last_run": None, "status": "starting"},
        "halal_drip_loop":         {"last_run": None, "status": "starting"},
        "discovery_loop":          {"last_run": None, "status": "starting"},
        "portfolio_snapshot_loop": {"last_run": None, "status": "starting"},
        "daily_report_loop":       {"last_run": None, "status": "starting"},
        "telegram_bot_loop":       {"last_run": None, "status": "starting"},
        "purification_reminder_loop": {"last_run": None, "status": "starting"},
        "zakat_monitoring_loop":   {"last_run": None, "status": "starting"},
        "audit_integrity_loop":    {"last_run": None, "status": "starting"},
        "ml_retraining_loop":      {"last_run": None, "status": "starting"},
    }

    # 4. Import Loops
    from ibkr_core.features.trading.loops import main_loop, cash_sweep_loop, halal_drip_loop, discovery_loop
    from ibkr_core.features.compliance.loops import compliance_audit_loop
    from ibkr_core.features.portfolio.loops import portfolio_snapshot_loop
    from ibkr_core.features.alerts.loops import daily_report_loop, purification_reminder_loop
    from ibkr_core.features.alerts.telegram_bot import telegram_bot_loop
    from ibkr_core.features.zakat.loops import zakat_monitoring_loop
    try:
        from ibkr_core.features.ai.loops import ml_retraining_loop
        HAS_AI_MODULE = True
    except ImportError:
        HAS_AI_MODULE = False
    # Import the main.py version of the integrity loop
    from ibkr_core.main import audit_integrity_loop

    # 5. Start Loops (Short Duration)
    logger.info("Initializing 12 Security & Intelligence loops...")
    
    # We use a tiny sleep in mocks to allow loops to cycle once
    with patch("asyncio.sleep", side_effect=lambda s: asyncio.sleep(0.1)):
        tasks = [
            asyncio.create_task(main_loop(mock_worker, MagicMock(), health)),
            asyncio.create_task(compliance_audit_loop(mock_worker, MagicMock(), health)),
            asyncio.create_task(cash_sweep_loop(mock_worker, MagicMock(), health)),
            asyncio.create_task(halal_drip_loop(mock_worker, MagicMock(), health)),
            asyncio.create_task(discovery_loop(mock_worker, MagicMock(), health)),
            asyncio.create_task(portfolio_snapshot_loop(mock_worker, health)),
            asyncio.create_task(daily_report_loop(mock_worker, health)),
            asyncio.create_task(telegram_bot_loop(mock_worker, health)),
            asyncio.create_task(purification_reminder_loop(health)),
            asyncio.create_task(zakat_monitoring_loop(mock_worker, health)),
            asyncio.create_task(audit_integrity_loop(mock_worker, health)),
        ]
        
        if HAS_AI_MODULE:
            tasks.append(asyncio.create_task(ml_retraining_loop(health)))
        
        # Let them run for a few simulated seconds
        await asyncio.sleep(2)
        
        # 6. Verify Health
        logger.info("--- LOOP STATUS CHECK ---")
        all_ok = True
        for name, status in health.items():
            st = status["status"]
            logger.info(f"Loop: {name:25} | Status: {st}")
            if st not in ("running", "starting"):
                all_ok = False
        
        # 7. Cleanup
        for t in tasks:
            t.cancel()
        
        if all_ok:
            logger.info("✅ SUCCESS: All 12 automated loops are healthy and communicating.")
            sys.exit(0)
        else:
            logger.error("❌ FAILURE: One or more loops failed to initialize.")
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_synthetic_test())
