<div align="center">

# 📊 Segment Analysis: Trade Segmentation and Probability Calculation

**Created:** December 5, 2024

---

## 🎯 Overview

This project analyzes Polymarket trading data by segmenting trades into four categories (Small, Medium, Large, Whale) based on trade size, and computes cumulative net positions and implied probabilities for each segment over time.

</div>

---

## 📁 Project Structure

```
Segment Analysis/
├── raw/                          # Input data
│   └── event_X/
│       ├── meta/
│       │   └── meta_*.csv
│       ├── trades/
│       │   └── *_trades.csv     # Multiple trade files per event
│       └── prices/
│           └── *_price.csv      # Market price history
├── output/                       # Generated outputs
│   └── event_X/
│       └── market_Y/
│           ├── small.csv         # Small segment trades
│           ├── medium.csv        # Medium segment trades
│           ├── large.csv         # Large segment trades
│           ├── whale.csv         # Whale segment trades
│           ├── small_daily_panel.csv
│           ├── medium_daily_panel.csv
│           ├── large_daily_panel.csv
│           ├── whale_daily_panel.csv
│           ├── merged_panel.csv  # All segments + market probability
│           └── plots/
│               ├── *_probabilities.png
│               ├── *_probabilities.pdf
│               └── *_probabilities.html
├── segment_trades.py             # Main processing script
├── plot_segment_probabilities.py # Visualization script
└── analyze_negative_and_user_positions.py # Analysis script
```

---

## 🔄 Processing Pipeline

### **Step 1: Event Selection** 📂

- **Input:** All event folders in `raw/`
- **Process:** Select first 10 events alphabetically
- **Output:** List of selected event directories

```python
# Select first 10 events (alphabetically sorted)
top_events = sorted(event_directories)[:10]
```

---

### **Step 2: Trade Segmentation** ✂️

For each event, we:

1. **Load all trade files** from `raw/event_X/trades/*.csv`
2. **Assign market_id** based on filename (each file = one market)
3. **Determine trade amount column** (tries: `trade_amount`, `amount`, `size`, `qty`, `quantity`)
4. **Segment trades** into 4 categories per market:

#### Segmentation Logic

**Whale Threshold:**
```
whale_threshold = mean(trade_amount) + 2 × std(trade_amount)
```

**For non-whale trades:**
- Compute 33rd and 66th percentiles
- **Small:** < 33rd percentile
- **Medium:** 33rd percentile ≤ amount < 66th percentile  
- **Large:** ≥ 66th percentile
- **Whale:** ≥ whale_threshold

**Special Cases:**
- If < 4 trades or all amounts identical → All marked as "Small"
- If std = 0 → No whales (threshold = ∞)

5. **Add day index** column:
   - Convert Unix timestamps to dates
   - Day 1 = earliest trade date
   - Day t = (trade_date - min_date).days + 1

6. **Save segmented files:**
   - `output/event_X/market_Y/{small,medium,large,whale}.csv`

---

### **Step 3: Daily Panel Calculation** 📈

For each market-segment combination:

#### Compute Cumulative Net Positions

**YES Net (per day):**
```
YES_net_t = Σ(BUY × size where outcome="Yes") - Σ(SELL × size where outcome="Yes")
```

**NO Net (per day):**
```
NO_net_t = Σ(BUY × size where outcome="No") - Σ(SELL × size where outcome="No")
```

**Cumulative Positions:**
```
H_Y_jt = Σ(YES_net_1 to YES_net_t)  # Cumulative YES net position
H_N_jt = Σ(NO_net_1 to NO_net_t)    # Cumulative NO net position
```

**Implied Probability:**
```
p_segment_t = H_Y_jt / (|H_Y_jt| + |H_N_jt|)
```

**Properties:**
- ✅ Bounded to [-1, 1]
- ✅ Positive = net YES position
- ✅ Negative = net NO position
- ✅ NaN when denominator = 0

**Forward-filling:** Missing days use previous day's cumulative values.

**Output:** `*_daily_panel.csv` with columns:
- `segment`, `market_id`, `day`, `H_Y_jt`, `H_N_jt`, `p_segment_t`

---

### **Step 4: Merge with Market Probability** 🔗

1. **Load all 4 segment daily panels** for a market
2. **Extract p_segment_t** → rename to `p_whale`, `p_large`, `p_medium`, `p_small`
3. **Load price CSV** from `raw/event_X/prices/*_price.csv`
4. **Convert price timestamps to day indices** (aligned with trade days)
5. **Merge on day** column
6. **Forward-fill** missing price days

**Output:** `merged_panel.csv` with columns:
- `day`, `p_whale`, `p_large`, `p_medium`, `p_small`, `p_market`

---

### **Step 5: Visualization** 📊

Generate publication-ready plots:

- **5 time series lines:**
  - 🐋 Whale segment probability
  - 🔶 Large segment probability
  - 🔷 Medium segment probability
  - 🔸 Small segment probability
  - ⚫ Market official probability

- **Features:**
  - Y-axis: Implied Probability [-1, 1]
  - X-axis: Day t
  - Horizontal line at y=0 (separates Buy/Sell regions)
  - "Buy" label (positive region)
  - "Sell" label (negative region)
  - Legend, grid, proper labels

- **Output formats:**
  - PNG (300 DPI, publication-ready)
  - PDF (vector format)
  - HTML (interactive Plotly)

---

## 📐 Key Formulas

### Segmentation Thresholds

```
whale_threshold = μ + 2σ

q33 = 33rd percentile of non-whale trades
q66 = 66th percentile of non-whale trades

Segment assignment:
  if trade_amount ≥ whale_threshold → Whale
  elif trade_amount ≥ q66 → Large
  elif trade_amount ≥ q33 → Medium
  else → Small
```

### Cumulative Net Positions

```
H_Y_jt = Σ_{s=1}^{t} [Σ(BUY × size | outcome="Yes") - Σ(SELL × size | outcome="Yes")]_s

H_N_jt = Σ_{s=1}^{t} [Σ(BUY × size | outcome="No") - Σ(SELL × size | outcome="No")]_s
```

### Implied Probability

```
p_segment_t = H_Y_jt / (|H_Y_jt| + |H_N_jt|)
```

**Where:**
- `H_Y_jt` = cumulative YES net position at day t
- `H_N_jt` = cumulative NO net position at day t
- Result bounded to [-1, 1]

---

## ⚙️ Assumptions & Design Decisions

### 1. **Segmentation by Trade Size** 💰
- **Assumption:** Trade size is a proxy for trader sophistication/value
- **Rationale:** Larger trades may indicate more informed or capital-rich traders
- **Future:** Consider user-based segmentation (high-value vs low-value users)

### 2. **Day Index Calculation** 📅
- **Assumption:** Day 1 = earliest trade in that market
- **Rationale:** Each market has its own timeline, aligned to its first trade
- **Note:** Days are forward-filled (missing days use previous values)

### 3. **Probability Bounding** 📏
- **Decision:** Use absolute values in denominator
- **Formula:** `p = H_Y / (|H_Y| + |H_N|)`
- **Rationale:** Ensures bounded result [-1, 1] even when H_Y and H_N have opposite signs
- **Interpretation:** 
  - Positive = net YES position
  - Negative = net NO position
  - Magnitude = proportion of activity

### 4. **Missing Data Handling** 🔄
- **Missing days:** Forward-filled with previous cumulative values
- **Missing segments:** NaN in merged panel (segment has no trades that day)
- **Missing prices:** Forward-filled with last known price

### 5. **Event Selection** 🎯
- **Current:** First 10 events alphabetically
- **Alternative:** Could rank by trade count (not currently used)

---

## 📊 Key Statistics

### Negative Probabilities
- **37.61%** of daily panel rows have negative p_segment_t
- **17.65%** have NaN (when H_Y + H_N ≤ 0)
- Occurs when segments have net selling pressure

### User Position Constraints
- **20.17%** of users sell more than they buy (in trade data)
- Suggests positions acquired through:
  - Transfers
  - Initial allocations
  - Airdrops
  - Missing trade data

---

## 🚀 Usage

### Run Full Pipeline

```bash
# Activate virtual environment
source .venv/bin/activate

# Run segmentation and daily panel calculation
python segment_trades.py
```

### Generate Plots

```bash
# Plot all markets
python plot_segment_probabilities.py

# Plot specific market
python plot_segment_probabilities.py output/event_X/market_Y/merged_panel.csv
```

### Analyze Statistics

```bash
# Analyze negative probabilities and user positions
python analyze_negative_and_user_positions.py
```

---

## 📦 Dependencies

- **pandas** - Data manipulation
- **matplotlib** - Static plotting
- **plotly** - Interactive plotting
- **seaborn** - Plot styling

Install with:
```bash
pip install pandas matplotlib plotly seaborn
```

---

## 📝 Output Files

### Per Market

1. **Segmented Trade Files:**
   - `small.csv`, `medium.csv`, `large.csv`, `whale.csv`
   - Contains original trade data + `segment` and `day` columns

2. **Daily Panel Files:**
   - `*_daily_panel.csv`
   - Columns: `segment`, `market_id`, `day`, `H_Y_jt`, `H_N_jt`, `p_segment_t`

3. **Merged Panel:**
   - `merged_panel.csv`
   - Columns: `day`, `p_whale`, `p_large`, `p_medium`, `p_small`, `p_market`

4. **Visualizations:**
   - `plots/*_probabilities.png` (static, high-res)
   - `plots/*_probabilities.pdf` (vector)
   - `plots/*_probabilities.html` (interactive)

### Global

- `market_summary.csv` - Summary statistics for all markets
- `day_calculation_test.txt` - Day calculation verification

---

## 🔍 Interpretation Guide

### Reading p_segment_t

- **p_segment_t > 0:** Net YES position (more YES buys than sells)
- **p_segment_t < 0:** Net NO position (more NO buys than sells)
- **|p_segment_t|:** Magnitude indicates proportion of activity
- **p_segment_t = 0:** Balanced YES/NO activity
- **p_segment_t = NaN:** No activity (H_Y + H_N = 0)

### Comparing Segments

- **Whale vs Small:** Compare large traders vs small traders
- **All segments vs Market:** Compare trader sentiment vs official market price
- **Trends over time:** Look for convergence/divergence patterns

---

## 🐛 Known Issues & Limitations

1. **Negative Probabilities:** 37.61% of values are negative (expected when net selling)
2. **User Constraints:** 20% of users sell more than they buy (positions from other sources)
3. **Segmentation:** Based on trade size, not user value (future improvement)
4. **Missing Data:** Some markets may have incomplete price data

---

## 📚 References

- **Data Source:** Polymarket trade and price data
- **Segmentation Method:** Percentile-based with whale threshold
- **Probability Calculation:** Net position ratio with absolute value normalization

---

<div align="center">

**Last Updated:** December 5, 2024

</div>

