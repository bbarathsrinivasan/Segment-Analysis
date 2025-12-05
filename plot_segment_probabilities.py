"""
Visualize segment probabilities and market probability over time.
Creates both static (Matplotlib) and interactive (Plotly) plots.
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_segment_probabilities_matplotlib(
    merged_panel_path: Path,
    output_dir: Path,
    market_name: str = None,
) -> None:
    """
    Create publication-ready static plot using Matplotlib.
    
    Args:
        merged_panel_path: Path to merged_panel.csv file
        output_dir: Directory to save output files
        market_name: Optional market name for title
    """
    # Load data
    df = pd.read_csv(merged_panel_path)
    
    # Remove rows where day is NaN
    df = df[df["day"].notna()].copy()
    df = df.sort_values("day").reset_index(drop=True)
    
    # Set up the plot with publication-ready styling
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Define colors for each segment
    colors = {
        "p_whale": "#1f77b4",  # Blue
        "p_large": "#ff7f0e",  # Orange
        "p_medium": "#2ca02c",  # Green
        "p_small": "#d62728",  # Red
        "p_market": "#000000",  # Black
    }
    
    # Plot each segment probability
    if "p_whale" in df.columns:
        ax.plot(
            df["day"],
            df["p_whale"],
            color=colors["p_whale"],
            linewidth=2,
            label="Whale",
            marker="o",
            markersize=4,
            alpha=0.8,
        )
    
    if "p_large" in df.columns:
        ax.plot(
            df["day"],
            df["p_large"],
            color=colors["p_large"],
            linewidth=2,
            label="Large",
            marker="s",
            markersize=4,
            alpha=0.8,
        )
    
    if "p_medium" in df.columns:
        ax.plot(
            df["day"],
            df["p_medium"],
            color=colors["p_medium"],
            linewidth=2,
            label="Medium",
            marker="^",
            markersize=4,
            alpha=0.8,
        )
    
    if "p_small" in df.columns:
        ax.plot(
            df["day"],
            df["p_small"],
            color=colors["p_small"],
            linewidth=2,
            label="Small",
            marker="v",
            markersize=4,
            alpha=0.8,
        )
    
    # Plot market probability
    if "p_market" in df.columns:
        ax.plot(
            df["day"],
            df["p_market"],
            color=colors["p_market"],
            linewidth=2.5,
            label="Market",
            linestyle="--",
            marker="D",
            markersize=5,
            alpha=0.9,
        )
    
    # Add horizontal line at y=0 to separate positive/negative
    ax.axhline(y=0, color="gray", linestyle="-", linewidth=1.5, alpha=0.5, zorder=0)
    
    # Add text labels for Buy/Sell regions
    y_min, y_max = ax.get_ylim()
    ax.text(
        0.02,
        0.95,
        "Buy",
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        color="green",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.3),
    )
    ax.text(
        0.02,
        0.05,
        "Sell",
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        color="red",
        verticalalignment="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral", alpha=0.3),
    )
    
    # Set axis limits and labels
    ax.set_xlim(df["day"].min() - 0.5, df["day"].max() + 0.5)
    ax.set_ylim(-1, 1)
    ax.set_xlabel("Day t", fontsize=14, fontweight="bold")
    ax.set_ylabel("Implied Probability", fontsize=14, fontweight="bold")
    
    # Set title
    if market_name:
        title = f"Segment Probabilities Over Time\n{market_name}"
    else:
        title = "Segment Probabilities Over Time"
    ax.set_title(title, fontsize=16, fontweight="bold", pad=20)
    
    # Add legend
    ax.legend(
        loc="best",
        fontsize=11,
        frameon=True,
        fancybox=True,
        shadow=True,
        framealpha=0.9,
    )
    
    # Add grid
    ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
    
    # Improve layout
    plt.tight_layout()
    
    # Save as PNG and PDF
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = merged_panel_path.parent.name
    
    png_path = output_dir / f"{base_name}_probabilities.png"
    pdf_path = output_dir / f"{base_name}_probabilities.pdf"
    
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.savefig(pdf_path, bbox_inches="tight")
    plt.close()
    
    print(f"Saved static plots: {png_path}, {pdf_path}")


def plot_segment_probabilities_plotly(
    merged_panel_path: Path,
    output_dir: Path,
    market_name: str = None,
) -> None:
    """
    Create interactive plot using Plotly.
    
    Args:
        merged_panel_path: Path to merged_panel.csv file
        output_dir: Directory to save output files
        market_name: Optional market name for title
    """
    # Load data
    df = pd.read_csv(merged_panel_path)
    
    # Remove rows where day is NaN
    df = df[df["day"].notna()].copy()
    df = df.sort_values("day").reset_index(drop=True)
    
    # Create figure
    fig = go.Figure()
    
    # Define colors and markers
    colors = {
        "p_whale": "#1f77b4",
        "p_large": "#ff7f0e",
        "p_medium": "#2ca02c",
        "p_small": "#d62728",
        "p_market": "#000000",
    }
    
    markers = {
        "p_whale": "circle",
        "p_large": "square",
        "p_medium": "triangle-up",
        "p_small": "triangle-down",
        "p_market": "diamond",
    }
    
    # Add traces for each segment
    if "p_whale" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["p_whale"],
                mode="lines+markers",
                name="Whale",
                line=dict(color=colors["p_whale"], width=2),
                marker=dict(size=6, symbol=markers["p_whale"]),
                hovertemplate="Day: %{x}<br>Whale: %{y:.4f}<extra></extra>",
            )
        )
    
    if "p_large" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["p_large"],
                mode="lines+markers",
                name="Large",
                line=dict(color=colors["p_large"], width=2),
                marker=dict(size=6, symbol=markers["p_large"]),
                hovertemplate="Day: %{x}<br>Large: %{y:.4f}<extra></extra>",
            )
        )
    
    if "p_medium" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["p_medium"],
                mode="lines+markers",
                name="Medium",
                line=dict(color=colors["p_medium"], width=2),
                marker=dict(size=6, symbol=markers["p_medium"]),
                hovertemplate="Day: %{x}<br>Medium: %{y:.4f}<extra></extra>",
            )
        )
    
    if "p_small" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["p_small"],
                mode="lines+markers",
                name="Small",
                line=dict(color=colors["p_small"], width=2),
                marker=dict(size=6, symbol=markers["p_small"]),
                hovertemplate="Day: %{x}<br>Small: %{y:.4f}<extra></extra>",
            )
        )
    
    # Add market probability
    if "p_market" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["day"],
                y=df["p_market"],
                mode="lines+markers",
                name="Market",
                line=dict(color=colors["p_market"], width=3, dash="dash"),
                marker=dict(size=7, symbol=markers["p_market"]),
                hovertemplate="Day: %{x}<br>Market: %{y:.4f}<extra></extra>",
            )
        )
    
    # Add horizontal line at y=0
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color="gray",
        line_width=1.5,
        opacity=0.5,
        annotation_text="",
    )
    
    # Add annotations for Buy/Sell regions
    fig.add_annotation(
        x=0.02,
        y=0.95,
        xref="paper",
        yref="paper",
        text="Buy",
        showarrow=False,
        font=dict(size=14, color="green", family="Arial Black"),
        bgcolor="lightgreen",
        bordercolor="green",
        borderwidth=1,
        borderpad=4,
    )
    
    fig.add_annotation(
        x=0.02,
        y=0.05,
        xref="paper",
        yref="paper",
        text="Sell",
        showarrow=False,
        font=dict(size=14, color="red", family="Arial Black"),
        bgcolor="lightcoral",
        bordercolor="red",
        borderwidth=1,
        borderpad=4,
    )
    
    # Update layout
    title_text = f"Segment Probabilities Over Time"
    if market_name:
        title_text += f"<br><sub>{market_name}</sub>"
    
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=18, family="Arial Black")),
        xaxis=dict(
            title=dict(text="Day t", font=dict(size=14, family="Arial")),
            showgrid=True,
            gridcolor="lightgray",
            gridwidth=1,
        ),
        yaxis=dict(
            title=dict(text="Implied Probability", font=dict(size=14, family="Arial")),
            range=[-1, 1],
            showgrid=True,
            gridcolor="lightgray",
            gridwidth=1,
        ),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="black",
            borderwidth=1,
            font=dict(size=11),
        ),
        hovermode="x unified",
        template="plotly_white",
        width=1200,
        height=800,
    )
    
    # Save as HTML
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = merged_panel_path.parent.name
    html_path = output_dir / f"{base_name}_probabilities.html"
    
    fig.write_html(str(html_path))
    print(f"Saved interactive plot: {html_path}")


def plot_market(
    merged_panel_path: Path,
    output_dir: Path = None,
    market_name: str = None,
) -> None:
    """
    Create both static and interactive plots for a single market.
    
    Args:
        merged_panel_path: Path to merged_panel.csv file
        output_dir: Directory to save output files (default: same as input file)
        market_name: Optional market name for title
    """
    if output_dir is None:
        output_dir = merged_panel_path.parent
    
    # Create plots directory
    plots_dir = output_dir / "plots"
    
    # Generate both versions
    plot_segment_probabilities_matplotlib(merged_panel_path, plots_dir, market_name)
    plot_segment_probabilities_plotly(merged_panel_path, plots_dir, market_name)


def plot_all_markets(output_root: Path) -> None:
    """
    Generate plots for all markets in the output directory.
    
    Args:
        output_root: Root directory containing market folders
    """
    merged_files = list(output_root.rglob("merged_panel.csv"))
    
    print(f"Found {len(merged_files)} merged panel files")
    
    for merged_file in merged_files:
        market_name = merged_file.parent.name
        print(f"\nPlotting: {market_name}")
        try:
            plot_market(merged_file, market_name=market_name)
        except Exception as e:
            print(f"Error plotting {market_name}: {e}")
            continue
    
    print("\nAll plots generated!")


def main():
    """Main function for command-line usage."""
    import sys
    
    base_dir = Path(__file__).resolve().parent
    output_root = base_dir / "output"
    
    if len(sys.argv) > 1:
        # Plot specific market file
        market_path = Path(sys.argv[1])
        if not market_path.exists():
            print(f"Error: File not found: {market_path}")
            return
        plot_market(market_path)
    else:
        # Plot all markets
        plot_all_markets(output_root)


if __name__ == "__main__":
    main()

