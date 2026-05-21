import argparse
import sys
import logging
from ibkr_core.features.compliance.screening import live_shariah_screen, check_shariah_compliance
from ibkr_core.features.compliance.schemas import ComplianceStatus

# Configure logging to be minimal for CLI
logging.basicConfig(level=logging.ERROR)

def main():
    parser = argparse.ArgumentParser(description="Quick Shariah screening for a ticker.")
    parser.add_argument("ticker", nargs="?", help="The stock ticker to screen (e.g. MSFT)")
    parser.add_argument("--detail", action="store_true", help="Show full source breakdown")
    
    # Test/Manual override flags (matching existing tests)
    parser.add_argument("--symbol", help=argparse.SUPPRESS)
    parser.add_argument("--debt", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--cash", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--revenue", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--prohibited-income", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--mkt-cap", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--sector", help=argparse.SUPPRESS)
    
    args = parser.parse_args()

    # Priority 1: Manual override (for tests)
    if args.symbol:
        symbol = args.symbol.upper()
        if all(v is not None for v in [args.debt, args.cash, args.revenue, args.prohibited_income, args.mkt_cap, args.sector]):
            result = check_shariah_compliance(
                symbol=symbol,
                debt=args.debt,
                cash=args.cash,
                revenue=args.revenue,
                prohibited_income=args.prohibited_income,
                mkt_cap=args.mkt_cap,
                sector=args.sector
            )
            # Fill in some gaps for display
            result.exchange = "N/A"
            result.data_source = "Manual Entry"
        else:
            result = live_shariah_screen(symbol)
    elif args.ticker:
        symbol = args.ticker.upper()
        result = live_shariah_screen(symbol)
    else:
        parser.print_help()
        sys.exit(0)
    
    try:
        status_color = "\033[92m" if result.is_compliant else "\033[91m"
        reset_color = "\033[0m"
        
        print(f"\n{status_color}=== {result.symbol} SHARIAH STATUS: {'COMPLIANT' if result.is_compliant else 'NON-COMPLIANT'} ==={reset_color}")
        if result.company_name:
            print(f"Company:  {result.company_name}")
        print(f"Sector:   {result.sector}")
        print(f"Exchange: {getattr(result, 'exchange', 'Unknown')}")
        print("-" * 40)
        
        print(f"Debt / Mkt Cap:   {result.debt_to_mkt_cap:.2%}")
        print(f"Cash / Mkt Cap:   {result.cash_to_mkt_cap:.2%}")
        print(f"Impure Revenue:   {result.impure_revenue_pct:.2%}")
        
        if not result.is_compliant and result.reason:
            print(f"\n{status_color}REASON:{reset_color} {result.reason}")
            
        if args.detail and getattr(result, 'sources_detail', None):
            print(f"\n{status_color}SOURCE BREAKDOWN:{reset_color}")
            for src in result.sources_detail:
                print(f"- {src.source}: {src.verdict} ({src.note or 'No note'})")
        
        print(f"\nData Source: {result.data_source}")
        if getattr(result, 'data_as_of', None):
            print(f"Data As Of:  {result.data_as_of} {'(STALE)' if getattr(result, 'data_stale', False) else ''}")
        print("-" * 40 + "\n")

    except Exception as e:
        print(f"\033[91mError screening {symbol}: {e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
