"""
Analyze two issues:
1. How often p_segment_t goes negative (when H_Y + H_N <= 0)
2. Whether users can sell more than they've bought (checking if cumulative sells > cumulative buys)
"""

from pathlib import Path
import pandas as pd


def analyze_negative_probabilities(output_root: Path) -> dict:
    """Analyze how often p_segment_t is negative or NaN."""
    stats = {
        "total_daily_panels": 0,
        "total_rows": 0,
        "negative_p_segment": 0,
        "nan_p_segment": 0,
        "zero_denominator": 0,
        "markets_with_negative": set(),
        "segments_with_negative": {"Small": 0, "Medium": 0, "Large": 0, "Whale": 0},
    }
    
    for event_dir in output_root.iterdir():
        if not event_dir.is_dir():
            continue
        
        for market_dir in event_dir.iterdir():
            if not market_dir.is_dir():
                continue
            
            for seg_name, file_name in [
                ("Small", "small_daily_panel.csv"),
                ("Medium", "medium_daily_panel.csv"),
                ("Large", "large_daily_panel.csv"),
                ("Whale", "whale_daily_panel.csv"),
            ]:
                panel_file = market_dir / file_name
                if not panel_file.exists():
                    continue
                
                try:
                    df = pd.read_csv(panel_file)
                    if df.empty or "p_segment_t" not in df.columns:
                        continue
                    
                    stats["total_daily_panels"] += 1
                    stats["total_rows"] += len(df)
                    
                    # Check for negative values
                    negative_mask = (df["p_segment_t"] < 0) & df["p_segment_t"].notna()
                    stats["negative_p_segment"] += negative_mask.sum()
                    
                    # Check for NaN values
                    nan_mask = df["p_segment_t"].isna()
                    stats["nan_p_segment"] += nan_mask.sum()
                    
                    # Check for zero denominator (H_Y + H_N <= 0)
                    if "H_Y_jt" in df.columns and "H_N_jt" in df.columns:
                        denominator = df["H_Y_jt"] + df["H_N_jt"]
                        zero_denom_mask = (denominator <= 0) & denominator.notna()
                        stats["zero_denominator"] += zero_denom_mask.sum()
                    
                    if negative_mask.any():
                        stats["markets_with_negative"].add((event_dir.name, market_dir.name, seg_name))
                        stats["segments_with_negative"][seg_name] += 1
                        
                except Exception as e:
                    print(f"Error reading {panel_file}: {e}")
                    continue
    
    return stats


def analyze_user_positions(raw_dir: Path) -> dict:
    """Check if users can sell more than they've bought."""
    stats = {
        "total_markets": 0,
        "total_users": 0,
        "users_with_excess_sells": 0,
        "markets_with_excess_sells": set(),
        "total_excess_sell_volume": 0.0,
        "examples": [],
    }
    
    # Process first 10 events for analysis
    event_dirs = sorted([d for d in raw_dir.iterdir() if d.is_dir()])[:10]
    
    for event_dir in event_dirs:
        trades_dir = event_dir / "trades"
        if not trades_dir.exists():
            continue
        
        for trade_file in trades_dir.glob("*.csv"):
            try:
                df = pd.read_csv(trade_file)
                if df.empty or "proxyWallet" not in df.columns or "side" not in df.columns or "size" not in df.columns:
                    continue
                
                stats["total_markets"] += 1
                
                # Ensure size is numeric
                df["size"] = pd.to_numeric(df["size"], errors="coerce")
                df = df[df["size"].notna()]
                
                if df.empty:
                    continue
                
                # Group by user (proxyWallet) and compute cumulative buys vs sells
                for user, user_trades in df.groupby("proxyWallet"):
                    stats["total_users"] += 1
                    
                    # Calculate total buys and sells for this user
                    total_buys = user_trades[user_trades["side"] == "BUY"]["size"].sum()
                    total_sells = user_trades[user_trades["side"] == "SELL"]["size"].sum()
                    
                    # Check if sells exceed buys
                    if total_sells > total_buys:
                        excess = total_sells - total_buys
                        stats["users_with_excess_sells"] += 1
                        stats["total_excess_sell_volume"] += excess
                        stats["markets_with_excess_sells"].add((event_dir.name, trade_file.stem))
                        
                        # Store example (limit to 10)
                        if len(stats["examples"]) < 10:
                            stats["examples"].append({
                                "event": event_dir.name,
                                "market": trade_file.stem,
                                "user": user,
                                "total_buys": total_buys,
                                "total_sells": total_sells,
                                "excess": excess,
                            })
                
            except Exception as e:
                print(f"Error processing {trade_file}: {e}")
                continue
    
    return stats


def main():
    base_dir = Path(__file__).resolve().parent
    output_root = base_dir / "output"
    raw_dir = base_dir / "raw"
    
    print("=" * 80)
    print("ANALYSIS 1: Negative p_segment_t Statistics")
    print("=" * 80)
    
    neg_stats = analyze_negative_probabilities(output_root)
    
    print(f"Total daily panel files analyzed: {neg_stats['total_daily_panels']}")
    print(f"Total rows across all panels: {neg_stats['total_rows']}")
    print(f"\nRows with negative p_segment_t: {neg_stats['negative_p_segment']}")
    print(f"  Percentage: {neg_stats['negative_p_segment'] / neg_stats['total_rows'] * 100:.2f}%")
    print(f"\nRows with NaN p_segment_t: {neg_stats['nan_p_segment']}")
    print(f"  Percentage: {neg_stats['nan_p_segment'] / neg_stats['total_rows'] * 100:.2f}%")
    print(f"\nRows with zero/negative denominator (H_Y + H_N <= 0): {neg_stats['zero_denominator']}")
    print(f"  Percentage: {neg_stats['zero_denominator'] / neg_stats['total_rows'] * 100:.2f}%")
    print(f"\nMarkets with at least one negative p_segment_t: {len(neg_stats['markets_with_negative'])}")
    print(f"\nNegative p_segment_t by segment:")
    for seg, count in neg_stats["segments_with_negative"].items():
        print(f"  {seg}: {count} markets")
    
    print("\n" + "=" * 80)
    print("ANALYSIS 2: User Position Analysis (Can users sell more than they buy?)")
    print("=" * 80)
    
    user_stats = analyze_user_positions(raw_dir)
    
    print(f"Total markets analyzed: {user_stats['total_markets']}")
    print(f"Total unique users: {user_stats['total_users']}")
    print(f"\nUsers with excess sells (sells > buys): {user_stats['users_with_excess_sells']}")
    print(f"  Percentage: {user_stats['users_with_excess_sells'] / user_stats['total_users'] * 100:.2f}%")
    print(f"\nMarkets with at least one user having excess sells: {len(user_stats['markets_with_excess_sells'])}")
    print(f"Total excess sell volume: {user_stats['total_excess_sell_volume']:.2f}")
    
    if user_stats['examples']:
        print(f"\nExample cases (first 10):")
        for i, ex in enumerate(user_stats['examples'], 1):
            print(f"\n  Example {i}:")
            print(f"    Event: {ex['event']}")
            print(f"    Market: {ex['market']}")
            print(f"    User: {ex['user']}")
            print(f"    Total Buys: {ex['total_buys']:.2f}")
            print(f"    Total Sells: {ex['total_sells']:.2f}")
            print(f"    Excess Sells: {ex['excess']:.2f}")
    
    print("\n" + "=" * 80)
    print("Analysis completed.")


if __name__ == "__main__":
    main()

