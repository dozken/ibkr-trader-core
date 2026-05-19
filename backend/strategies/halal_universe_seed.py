"""Reference halal universe — small public seed list.

Standards-based: tickers chosen for low debt-to-asset ratio, no interest-bearing
revenue, no haram sectors (alcohol, gambling, conventional banking, defense,
adult content, tobacco, pork). This is a *starting point*, NOT a substitute for
running AAOIFI screening at runtime. Compliance ratios change quarterly with
earnings; always re-screen before placing orders.

Private forks of this bot may ship a larger, actively-curated universe and
override this list by exporting `SEED_UNIVERSE` / `REGIONAL_HALAL` from
`backend.features.ai.halal_universe`.
"""
from __future__ import annotations

# US large-caps that historically pass AAOIFI screening (verify before trading)
SEED_UNIVERSE: list[str] = [
    "AAPL",   # Apple — tech hardware
    "MSFT",   # Microsoft — software
    "GOOGL",  # Alphabet — internet
    "META",   # Meta — internet
    "NVDA",   # Nvidia — semis
    "AMD",    # AMD — semis
    "AVGO",   # Broadcom — semis
    "ASML",   # ASML — semis equip (ADR)
    "TSM",    # TSMC — semis (ADR)
    "ADBE",   # Adobe — software
    "CRM",    # Salesforce — software
    "ORCL",   # Oracle — software (check leverage)
    "TSLA",   # Tesla — autos/energy
    "LIN",    # Linde — industrial gases
    "ABT",    # Abbott Labs — healthcare
    "JNJ",    # Johnson & Johnson — healthcare
    "LLY",    # Eli Lilly — pharma
    "UNH",    # UnitedHealth — managed care (re-screen)
    "TMO",    # Thermo Fisher — life sciences
    "DHR",    # Danaher — life sciences
]

# Regional grouping for /api/system/markets endpoint.
# Add your own region keys for non-US exchanges as you screen them.
REGIONAL_HALAL: dict[str, list[str]] = {
    "US": SEED_UNIVERSE,
}
