import matplotlib.pyplot as plt

def _plot_dynamic_dashboard(df, ticker, strategy_name):
    """
    A purely dynamic visualizer. It reads the columns in your dataframe and 
    automatically calculates how many panes to draw and where to put them.
    """
    
    # 1. THE SORTER: Scan the DataFrame to see what tools we are using today
    has_equity = 'Equity' in df.columns
    
    # Add any future oscillators to this list! The engine will auto-detect them.
    supported_oscillators = ['RSI', 'MACD', 'ATR'] 
    active_oscillators = [osc for osc in supported_oscillators if osc in df.columns]
    
    # 2. THE GRID BUILDER: Calculate exact Matplotlib dimensions
    total_panes = 1 + len(active_oscillators) + (1 if has_equity else 0)
    
    # Give the Price chart a height of 3, and all lower panes a height of 1
    height_ratios = [3] + [1] * (total_panes - 1)
    
    # Generate the grid dynamically!
    fig, axes = plt.subplots(total_panes, 1, figsize=(14, 4 * total_panes), 
                             gridspec_kw={'height_ratios': height_ratios}, 
                             sharex=True)
    
    # Failsafe: If there is only 1 pane, Matplotlib doesn't return a list. Let's force it to be a list.
    if total_panes == 1:
        axes = [axes]
        
    fig.suptitle(f"{strategy_name} Deep Dive: {ticker.upper()}", fontsize=18, fontweight='bold')
    
    current_pane = 0  # This acts as our "Elevator" moving down the chart

    # ==========================================
    # --- PANE 1: PRICE & DYNAMIC OVERLAYS   ---
    # ==========================================
    ax_price = axes[current_pane]
    ax_price.plot(df.index, df['Close'], label='Close Price', color='black', alpha=0.4)
    
    # Auto-plot any Moving Averages or Bands found in the data
    overlay_colors = {'MA_short': 'blue', 'MA_long': 'red', 'Upper_Band': 'gray', 'Lower_Band': 'gray'}
    for col, color in overlay_colors.items():
        if col in df.columns:
            ax_price.plot(df.index, df[col], label=col.replace('_', ' '), color=color, alpha=0.7)
            
    # Auto-plot Buy/Sell Signals
    if 'Signal' in df.columns:
        buys = df[(df['Signal'] == 1) & (df['Signal'].shift(1) != 1)]
        sells = df[(df['Signal'] == 0) & (df['Signal'].shift(1) == 1)]
        ax_price.scatter(buys.index, buys['Close'], marker='^', color='green', s=120, label='Entry Signal', zorder=5)
        ax_price.scatter(sells.index, sells['Close'], marker='v', color='red', s=120, label='Exit Signal', zorder=5)
        
    ax_price.set_ylabel("Price ($)")
    ax_price.legend(loc="upper left")
    ax_price.grid(True, alpha=0.2)
    
    current_pane += 1 # Move the elevator down to the next row

    # ==========================================
    # --- DYNAMIC OSCILLATOR PANES           ---
    # ==========================================
    for osc in active_oscillators:
        ax_osc = axes[current_pane]
        
        # We define the specific visual style for each supported oscillator here
        if osc == 'RSI':
            ax_osc.plot(df.index, df['RSI'], color='purple', label='RSI')
            ax_osc.axhline(70, color='red', linestyle='--', alpha=0.3)
            ax_osc.axhline(30, color='green', linestyle='--', alpha=0.3)
            ax_osc.fill_between(df.index, 70, 100, color='red', alpha=0.05)
            ax_osc.fill_between(df.index, 0, 30, color='green', alpha=0.05)
            ax_osc.set_ylim(0, 100)
            
        elif osc == 'MACD':
            # Ready for you whenever you build a MACD strategy!
            ax_osc.plot(df.index, df['MACD'], color='orange', label='MACD')
            
        ax_osc.set_ylabel(osc)
        ax_osc.legend(loc="upper left")
        ax_osc.grid(True, alpha=0.2)
        
        current_pane += 1 # Move the elevator down again

    # ==========================================
    # --- FINAL PANE: EQUITY CURVE           ---
    # ==========================================
    if has_equity:
        ax_eq = axes[current_pane]
        ax_eq.plot(df.index, df['Equity'], color='darkgreen', label='Strategy Equity')
        ax_eq.fill_between(df.index, df['Equity'], color='green', alpha=0.1)
        ax_eq.set_ylabel("Portfolio Value ($)")
        ax_eq.legend(loc="upper left")
        ax_eq.grid(True, alpha=0.2)
        
    # Final cleanup
    axes[-1].set_xlabel("Date")
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

# =====================================================================
# PUBLIC FUNCTIONS (Routers to the Dynamic Template)
# =====================================================================

def plot_ma_signals(df, ticker):
    _plot_dynamic_dashboard(df, ticker, strategy_name="Pure MA")

def plot_rsi_signals(df, ticker):
    _plot_dynamic_dashboard(df, ticker, strategy_name="Pure RSI")

def plot_combo_signals(df, ticker):
    _plot_dynamic_dashboard(df, ticker, strategy_name="Combo")