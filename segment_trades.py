from pathlib import Path

import pandas as pd


def find_event_directories(raw_dir: Path) -> list[Path]:
    """
    Return a list of event directories under raw_dir.
    Ignores non-directory entries.
    """
    return sorted([p for p in raw_dir.iterdir() if p.is_dir()])


def count_trades_in_event(event_dir: Path) -> int:
    """
    Return number of trades for this event.

    In the current folder structure, each event has:
        raw/event_X/trades/*.csv

    where each CSV contains trades for a single market/contract.
    We count all rows across every CSV under the trades/ subfolder.
    If there are no readable CSVs, returns 0.
    """
    trades_dir = event_dir / "trades"
    if not trades_dir.exists() or not trades_dir.is_dir():
        return 0

    total = 0
    for csv_path in trades_dir.glob("*.csv"):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            # Robust to malformed or unreadable CSVs
            continue
        total += len(df)

    return total


def select_top_events(raw_dir: Path, top_n: int = 10) -> list[Path]:
    """
    Select events under raw_dir.

    NOTE (customized for this project):
    Instead of ranking by trade count, we simply take the first `top_n`
    event directories in sorted (alphabetical) order.
    """
    events = find_event_directories(raw_dir)
    # Take the first `top_n` events (already sorted by name in find_event_directories)
    return events[:top_n]


def determine_amount_column(df: pd.DataFrame) -> str:
    """
    Determine which column represents trade amount.
    Tries a few common names; raises ValueError if none found.
    """
    candidate_cols = ["trade_amount", "amount", "size", "qty", "quantity"]
    for col in candidate_cols:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not find a trade amount column in trades.csv. "
        f"Tried: {candidate_cols}"
    )


def add_segment_column(df_market: pd.DataFrame, amount_col: str) -> pd.DataFrame:
    """
    Add a 'segment' column with values in {'Small', 'Medium', 'Large', 'Whale'}
    for a single market's trades.

    - whale_threshold = mean + 2 * std (per market)
    - For non-whales, compute 33rd and 66th percentiles and segment into
      Small/Medium/Large.
    - Handle small or degenerate markets robustly.
    """
    df = df_market.copy()

    # Ensure numeric amount column
    amt = pd.to_numeric(df[amount_col], errors="coerce")

    # If too few valid trades or all amounts identical, just mark all as Small
    valid_amt = amt.dropna()
    if len(valid_amt) < 4 or valid_amt.nunique() == 1:
        df["segment"] = "Small"
        # Use max amount as a stand-in whale threshold for summary purposes
        whale_threshold = valid_amt.max() if len(valid_amt) > 0 else float("nan")
        df["whale_threshold"] = whale_threshold
        return df

    mean = valid_amt.mean()
    std = valid_amt.std()

    # If std is NaN or 0, use a very high threshold so no whales, or fall back
    if pd.isna(std) or std == 0:
        whale_threshold = float("inf")
    else:
        whale_threshold = mean + 2 * std

    is_whale = amt >= whale_threshold

    non_whale_amt = amt[~is_whale & amt.notna()]
    if len(non_whale_amt) == 0:
        # All trades are whales
        df["segment"] = "Whale"
        df["whale_threshold"] = whale_threshold
        return df

    q33, q66 = non_whale_amt.quantile([0.33, 0.66])

    # Initialize all as Small by default
    segment = pd.Series("Small", index=df.index)

    # Large & Medium are only defined for non-whale trades
    large_mask = (~is_whale) & (amt >= q66)
    medium_mask = (~is_whale) & (amt >= q33) & (amt < q66)
    small_mask = (~is_whale) & (amt < q33)

    segment[large_mask] = "Large"
    segment[medium_mask] = "Medium"
    segment[small_mask] = "Small"
    segment[is_whale] = "Whale"

    df["segment"] = segment
    # Store the scalar whale_threshold on all rows for convenience when summarizing
    df["whale_threshold"] = whale_threshold
    return df


def add_day_column(df_market: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    """
    Add a 'day' column representing day index (1, 2, ...) relative to the
    earliest date in this market's trades.
    """
    df = df_market.copy()

    if timestamp_col not in df.columns:
        raise ValueError(
            f"Expected a '{timestamp_col}' column in trades.csv but did not find it."
        )

    # Convert Unix timestamps (integers) to datetime using unit='s'
    ts = pd.to_datetime(df[timestamp_col], unit='s', errors="coerce")
    # Compute based on valid timestamps only
    valid_ts = ts.dropna()
    if len(valid_ts) == 0:
        # No valid timestamps; fill day with NaN
        df["day"] = pd.NA
        return df

    min_date = valid_ts.dt.date.min()
    # Compute day index where possible
    day_index = ts.dt.date.map(lambda d: (d - min_date).days + 1 if pd.notna(d) else pd.NA)
    df["day"] = day_index
    return df


def process_event(event_dir: Path, output_root: Path) -> list[dict]:
    """
    For a single event directory:
      - Load trades.csv
      - For each market_id, segment trades and add day column
      - Save 4 CSVs (small, medium, large, whale) under
        output_root/event_X/market_Y/
    """
    # In this folder structure, trades are stored in multiple files:
    #   raw/event_X/trades/*.csv
    # Each CSV corresponds to a single market/contract. We will:
    #   - read all CSVs
    #   - add a synthetic 'market_id' column based on the file stem
    #   - concatenate into one trades DataFrame
    trades_dir = event_dir / "trades"
    if not trades_dir.exists() or not trades_dir.is_dir():
        # Skip events without trades directory
        return []

    frames: list[pd.DataFrame] = []
    for csv_path in sorted(trades_dir.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            # Skip unreadable CSVs robustly
            continue

        # Use the file stem (without extension) as a per-market identifier.
        # This gives a unique market_id per contract/question within the event.
        df = df.copy()
        df["market_id"] = csv_path.stem
        frames.append(df)

    if not frames:
        # No readable trade files for this event
        return []

    trades = pd.concat(frames, ignore_index=True)

    # Determine amount column once per event
    try:
        amount_col = determine_amount_column(trades)
    except ValueError:
        # If we cannot identify trade amount column, skip this event
        return []

    event_name = event_dir.name
    event_output_dir = output_root / event_name

    summary_rows: list[dict] = []

    for market_id, df_market in trades.groupby("market_id"):
        # Segment trades
        df_seg = add_segment_column(df_market, amount_col=amount_col)
        # Add day column
        df_seg = add_day_column(df_seg, timestamp_col="timestamp")

        # Prepare output directory for this market
        market_dir_name = str(market_id)
        market_output_dir = event_output_dir / market_dir_name
        market_output_dir.mkdir(parents=True, exist_ok=True)

        # Split into 4 segments and save
        segment_dfs = {}
        for seg_name, file_name in [
            ("Small", "small.csv"),
            ("Medium", "medium.csv"),
            ("Large", "large.csv"),
            ("Whale", "whale.csv"),
        ]:
            df_seg_part = df_seg[df_seg["segment"] == seg_name]
            segment_dfs[seg_name] = df_seg_part
            # If there are no trades of this segment, still write an empty file
            # with the appropriate columns for consistency.
            out_path = market_output_dir / file_name
            df_seg_part.to_csv(out_path, index=False)

        # Build per-market summary row
        total_trades = len(df_seg)

        def _count(seg: str) -> int:
            return len(segment_dfs.get(seg, []))

        def _volume(seg: str) -> float:
            df_part = segment_dfs.get(seg)
            if df_part is None or df_part.empty:
                return 0.0
            return float(pd.to_numeric(df_part[amount_col], errors="coerce").fillna(0).sum())

        def _max(seg: str) -> float:
            df_part = segment_dfs.get(seg)
            if df_part is None or df_part.empty:
                return float("nan")
            return float(pd.to_numeric(df_part[amount_col], errors="coerce").max())

        small_count = _count("Small")
        medium_count = _count("Medium")
        large_count = _count("Large")
        whale_count = _count("Whale")

        small_volume = _volume("Small")
        medium_volume = _volume("Medium")
        large_volume = _volume("Large")
        whale_volume = _volume("Whale")

        total_volume = small_volume + medium_volume + large_volume + whale_volume
        if total_volume > 0:
            small_share = small_volume / total_volume
            medium_share = medium_volume / total_volume
            large_share = large_volume / total_volume
            whale_share = whale_volume / total_volume
        else:
            small_share = medium_share = large_share = whale_share = float("nan")

        small_max = _max("Small")
        medium_max = _max("Medium")
        large_max = _max("Large")
        whale_threshold = float(
            df_seg["whale_threshold"].iloc[0]
        ) if "whale_threshold" in df_seg.columns and len(df_seg) > 0 else float("nan")

        # Metadata: slugs and titles if present
        market_id_str = str(market_id)
        market_slug = (
            str(df_market["slug"].iloc[0])
            if "slug" in df_market.columns and len(df_market) > 0
            else market_id_str
        )
        event_slug = (
            str(df_market["eventSlug"].iloc[0])
            if "eventSlug" in df_market.columns and len(df_market) > 0
            else event_name
        )
        market_title = (
            str(df_market["title"].iloc[0])
            if "title" in df_market.columns and len(df_market) > 0
            else market_slug
        )
        # If we don't have a separate event title column, reuse market_title as a proxy
        event_title = market_title

        summary_rows.append(
            {
                "market_id": market_id_str,
                "event_slug": event_slug,
                "market_slug": market_slug,
                "event_title": event_title,
                "market_title": market_title,
                "small_count": small_count,
                "medium_count": medium_count,
                "large_count": large_count,
                "whale_count": whale_count,
                "total_trades": total_trades,
                "small_volume": small_volume,
                "medium_volume": medium_volume,
                "large_volume": large_volume,
                "whale_volume": whale_volume,
                "small_volume_share": small_share,
                "medium_volume_share": medium_share,
                "large_volume_share": large_share,
                "whale_volume_share": whale_share,
                "small_max": small_max,
                "medium_max": medium_max,
                "large_max": large_max,
                "whale_threshold": whale_threshold,
            }
        )

    return summary_rows


def compute_daily_panel(output_root: Path) -> None:
    """
    Compute cumulative H_Y and H_N daily panel for each market and segment.
    
    For each (market_id, segment, day):
    - H_Y_jt = cumulative sum of (YES buys - YES sells) for segment j, market, up to day t
    - H_N_jt = cumulative sum of (NO buys - NO sells) for segment j, market, up to day t
    
    Creates one daily panel file per segment per market:
    - output/event_X/market_Y/{small,medium,large,whale}_daily_panel.csv
    """
    print("\nComputing daily panels (H_Y and H_N)...")
    
    # Find all market directories
    for event_dir in output_root.iterdir():
        if not event_dir.is_dir():
            continue
        
        for market_dir in event_dir.iterdir():
            if not market_dir.is_dir():
                continue
            
            # Process each segment file
            for seg_name, file_name in [
                ("Small", "small.csv"),
                ("Medium", "medium.csv"),
                ("Large", "large.csv"),
                ("Whale", "whale.csv"),
            ]:
                segment_csv = market_dir / file_name
                if not segment_csv.exists():
                    continue
                
                try:
                    # Load segment data
                    df = pd.read_csv(segment_csv)
                    
                    if df.empty or "day" not in df.columns or "side" not in df.columns or "outcome" not in df.columns or "size" not in df.columns:
                        continue
                    
                    # Ensure size is numeric
                    df["size"] = pd.to_numeric(df["size"], errors="coerce")
                    df = df[df["size"].notna()]
                    
                    if df.empty:
                        continue
                    
                    market_id = df["market_id"].iloc[0] if "market_id" in df.columns else market_dir.name
                    
                    # Group by day and compute daily net flows
                    daily_data = []
                    
                    # Get all days in this market-segment (including missing days to fill)
                    all_days = sorted(df["day"].dropna().unique())
                    if len(all_days) == 0:
                        continue
                    
                    min_day = int(all_days[0])
                    max_day = int(all_days[-1])
                    
                    # Initialize cumulative sums
                    cum_H_Y = 0.0
                    cum_H_N = 0.0
                    
                    # Process each day from min_day to max_day
                    for day in range(min_day, max_day + 1):
                        # Filter trades for this day
                        day_trades = df[df["day"] == day].copy()
                        
                        if not day_trades.empty:
                            # Calculate YES net for this day
                            yes_buys = day_trades[(day_trades["side"] == "BUY") & (day_trades["outcome"] == "Yes")]["size"].sum()
                            yes_sells = day_trades[(day_trades["side"] == "SELL") & (day_trades["outcome"] == "Yes")]["size"].sum()
                            yes_net = yes_buys - yes_sells
                            
                            # Calculate NO net for this day
                            no_buys = day_trades[(day_trades["side"] == "BUY") & (day_trades["outcome"] == "No")]["size"].sum()
                            no_sells = day_trades[(day_trades["side"] == "SELL") & (day_trades["outcome"] == "No")]["size"].sum()
                            no_net = no_buys - no_sells
                            
                            # Update cumulative sums
                            cum_H_Y += yes_net
                            cum_H_N += no_net
                        
                        # Forward-fill: if no trades on this day, use previous cumulative values
                        # (cum_H_Y and cum_H_N already contain the previous values)
                        
                        daily_data.append({
                            "segment": seg_name,
                            "market_id": market_id,
                            "day": day,
                            "H_Y_jt": cum_H_Y,
                            "H_N_jt": cum_H_N,
                        })
                    
                    # Create DataFrame for this segment and market
                    daily_panel = pd.DataFrame(daily_data)
                    
                    # Compute p_segment_t = H_Y_jt / (abs(H_Y_jt) + abs(H_N_jt)) if denominator > 0 else NaN
                    # Use absolute values to ensure bounded result to [-1, 1]
                    denominator = daily_panel["H_Y_jt"].abs() + daily_panel["H_N_jt"].abs()
                    daily_panel["p_segment_t"] = daily_panel["H_Y_jt"].div(denominator).where(denominator > 0)
                    
                    # Save to file
                    output_file = market_dir / f"{seg_name.lower()}_daily_panel.csv"
                    daily_panel.to_csv(output_file, index=False)
                    
                except Exception as e:
                    print(f"Error processing {segment_csv}: {e}")
                    continue
    
    print("Daily panel computation completed.")


def merge_segment_panels_with_market_prob(output_root: Path, raw_dir: Path) -> None:
    """
    Merge all segment daily panels with official market probability from price CSV files.
    
    For each market:
    - Load all four segment daily panel files (whale, large, medium, small)
    - Extract p_segment_t from each and rename to p_whale, p_large, p_medium, p_small
    - Load corresponding price CSV file and convert to day indices
    - Merge on day column
    - Save as merged_panel.csv
    """
    print("\nMerging segment panels with market probabilities...")
    
    # Find all market directories
    for event_dir in output_root.iterdir():
        if not event_dir.is_dir():
            continue
        
        event_name = event_dir.name
        event_raw_dir = raw_dir / event_name
        
        for market_dir in event_dir.iterdir():
            if not market_dir.is_dir():
                continue
            
            try:
                # Load all four segment daily panels
                segment_panels = {}
                for seg_name, file_name in [
                    ("whale", "whale_daily_panel.csv"),
                    ("large", "large_daily_panel.csv"),
                    ("medium", "medium_daily_panel.csv"),
                    ("small", "small_daily_panel.csv"),
                ]:
                    panel_file = market_dir / file_name
                    if panel_file.exists():
                        df = pd.read_csv(panel_file)
                        if not df.empty and "day" in df.columns and "p_segment_t" in df.columns:
                            segment_panels[seg_name] = df[["day", "p_segment_t"]].copy()
                            segment_panels[seg_name].rename(columns={"p_segment_t": f"p_{seg_name}"}, inplace=True)
                
                if not segment_panels:
                    continue
                
                # Get market_id to find corresponding price file
                # Try to get market_id from one of the segment panels
                sample_panel = next(iter(segment_panels.values()))
                market_id = market_dir.name
                
                # Remove _trades suffix if present to match price file naming
                market_slug = market_id.replace("_trades", "")
                
                # Find corresponding price file
                prices_dir = event_raw_dir / "prices"
                price_file = None
                if prices_dir.exists():
                    # Try exact match first
                    price_file = prices_dir / f"{market_slug}_price.csv"
                    if not price_file.exists():
                        # Try without _price suffix
                        price_file = prices_dir / f"{market_slug}.csv"
                    if not price_file.exists():
                        # Try to find by pattern
                        for pf in prices_dir.glob(f"*{market_slug}*"):
                            if pf.suffix == ".csv":
                                price_file = pf
                                break
                
                # Merge all segment panels on day
                merged = None
                for seg_name, df in segment_panels.items():
                    if merged is None:
                        merged = df[["day"]].copy()
                    merged = merged.merge(df[["day", f"p_{seg_name}"]], on="day", how="outer")
                
                # Sort by day
                merged = merged.sort_values("day").reset_index(drop=True)
                
                # Add market probability if price file exists
                if price_file and price_file.exists():
                    try:
                        price_df = pd.read_csv(price_file)
                        if not price_df.empty and "timestamp" in price_df.columns and "price" in price_df.columns:
                            # Convert timestamps to day indices
                            # First, we need to find the earliest timestamp from trades to align days
                            # Load one of the segment CSV files to get the earliest trade timestamp
                            segment_csv = market_dir / "small.csv"
                            if not segment_csv.exists():
                                segment_csv = market_dir / "medium.csv"
                            if not segment_csv.exists():
                                segment_csv = market_dir / "large.csv"
                            if not segment_csv.exists():
                                segment_csv = market_dir / "whale.csv"
                            
                            if segment_csv.exists():
                                trades_df = pd.read_csv(segment_csv)
                                if "timestamp" in trades_df.columns and not trades_df.empty:
                                    # Get earliest timestamp from trades
                                    trade_timestamps = pd.to_datetime(trades_df["timestamp"], unit='s', errors="coerce")
                                    valid_trade_ts = trade_timestamps.dropna()
                                    if len(valid_trade_ts) > 0:
                                        min_trade_date = valid_trade_ts.dt.date.min()
                                        
                                        # Convert price timestamps to day indices
                                        price_timestamps = pd.to_datetime(price_df["timestamp"], unit='s', errors="coerce")
                                        price_df["date"] = price_timestamps.dt.date
                                        price_df = price_df[price_df["date"].notna()].copy()
                                        
                                        if not price_df.empty:
                                            price_df["day"] = price_df["date"].apply(
                                                lambda d: (d - min_trade_date).days + 1 if pd.notna(d) else pd.NA
                                            )
                                            
                                            # Group by day and take the last price of each day (or average)
                                            price_by_day = price_df.groupby("day")["price"].last().reset_index()
                                            price_by_day.rename(columns={"price": "p_market"}, inplace=True)
                                            
                                            # Merge with segment panels
                                            merged = merged.merge(price_by_day, on="day", how="outer")
                                            
                                            # Forward-fill p_market for missing days
                                            merged["p_market"] = merged["p_market"].ffill()
                                            
                                            # Sort again after merge
                                            merged = merged.sort_values("day").reset_index(drop=True)
                    except Exception as e:
                        print(f"Error loading price file {price_file}: {e}")
                
                # Ensure all required columns exist (fill with NaN if missing)
                for col in ["p_whale", "p_large", "p_medium", "p_small", "p_market"]:
                    if col not in merged.columns:
                        merged[col] = pd.NA
                
                # Reorder columns: day, p_whale, p_large, p_medium, p_small, p_market
                column_order = ["day"]
                for col in ["p_whale", "p_large", "p_medium", "p_small", "p_market"]:
                    if col in merged.columns:
                        column_order.append(col)
                
                merged = merged[column_order]
                
                # Save merged panel
                output_file = market_dir / "merged_panel.csv"
                merged.to_csv(output_file, index=False)
                
            except Exception as e:
                print(f"Error merging panels for {market_dir}: {e}")
                continue
    
    print("Segment panel merge completed.")


def main():
    base_dir = Path(__file__).resolve().parent
    raw_dir = base_dir / "raw"
    output_root = base_dir / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    if not raw_dir.exists():
        raise SystemExit(f"Raw directory not found: {raw_dir}")

    # STEP 1 – select top 10 events by trade count
    top_events = select_top_events(raw_dir, top_n=10)
    if not top_events:
        print("No events with valid trades.csv found.")
        return

    print("Selected events (top by trade count):")
    for ev in top_events:
        print(f" - {ev.name}")

    # STEP 3–5 – process each selected event and accumulate per-market summaries
    all_summary_rows: list[dict] = []
    for event_dir in top_events:
        print(f"Processing event: {event_dir.name}")
        event_rows = process_event(event_dir, output_root=output_root)
        all_summary_rows.extend(event_rows)

    # Save global summary over all markets across all selected events
    if all_summary_rows:
        summary_df = pd.DataFrame(all_summary_rows)
        summary_path = output_root / "market_summary.csv"
        summary_df.to_csv(summary_path, index=False)
        print(f"Market-level summary written to: {summary_path}")
    else:
        print("No market summaries to write (no valid trades processed).")

    # Test output: Show day distributions for a few sample markets
    # Collect output lines to write to file
    test_output_lines = []
    test_output_lines.append("="*80)
    test_output_lines.append("DAY CALCULATION TEST OUTPUT")
    test_output_lines.append("="*80)
    
    # Find a few sample output files to test
    sample_markets = []
    for event_dir in top_events[:3]:  # Check first 3 events
        event_output_dir = output_root / event_dir.name
        if not event_output_dir.exists():
            continue
        for market_dir in event_output_dir.iterdir():
            if market_dir.is_dir():
                small_csv = market_dir / "small.csv"
                if small_csv.exists():
                    sample_markets.append((event_dir.name, market_dir.name, small_csv))
                    if len(sample_markets) >= 5:  # Get 5 sample markets
                        break
        if len(sample_markets) >= 5:
            break
    
    for event_name, market_name, csv_path in sample_markets:
        try:
            # Load one of the segment files (using small.csv as representative)
            df = pd.read_csv(csv_path)
            
            if "day" not in df.columns or "timestamp" not in df.columns:
                continue
            
            # Convert timestamps to dates for display
            timestamps = pd.to_datetime(df["timestamp"], unit='s', errors="coerce")
            valid_ts = timestamps.dropna()
            
            if len(valid_ts) == 0:
                continue
            
            min_date = valid_ts.min().date()
            max_date = valid_ts.max().date()
            unique_days = sorted(df["day"].dropna().unique())
            day_counts = df["day"].value_counts().sort_index()
            
            test_output_lines.append(f"\nMarket: {market_name}")
            test_output_lines.append(f"  Event: {event_name}")
            test_output_lines.append(f"  Date range: {min_date} to {max_date} ({len(unique_days)} unique days)")
            test_output_lines.append(f"  Day distribution:")
            for day in unique_days[:10]:  # Show first 10 days
                count = day_counts.get(day, 0)
                test_output_lines.append(f"    Day {day}: {count} trades")
            if len(unique_days) > 10:
                test_output_lines.append(f"    ... ({len(unique_days) - 10} more days)")
                
        except Exception as e:
            test_output_lines.append(f"Error reading {csv_path}: {e}")
            continue
    
    test_output_lines.append("\n" + "="*80)
    
    # Write test output to file
    test_output_path = output_root / "day_calculation_test.txt"
    with open(test_output_path, "w") as f:
        f.write("\n".join(test_output_lines))
    
    print(f"Day calculation test output written to: {test_output_path}")
    
    # Compute daily panels (H_Y and H_N) for all markets and segments
    compute_daily_panel(output_root)
    
    # Merge segment panels with market probabilities
    merge_segment_panels_with_market_prob(output_root, raw_dir)
    
    print("Processing completed. Output written under 'output/'.")


if __name__ == "__main__":
    main()


