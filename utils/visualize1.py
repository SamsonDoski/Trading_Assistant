import matplotlib.pyplot as plt

def plot_ma_signals(df, ticker):
    plt.figure(figsize=(14, 7))

    #plot closing price and moving averages

    plt.plot(df.index, df['Close'], label='Close Price', color='black', alpha=0.7)
    plt.plot(df.index, df['MA_short'], label='Short MA', color='blue', linestyle='--')
    plt.plot(df.index, df['MA_long'], label='Long MA', color='red', linestyle='-')

    # Buy Signals
    plt.scatter(df.index[df['Signal'] == 1], df['Close'][df['Signal'] == 1], label ='Buy'\
                , marker='^', color="green", s=100)

    # Sell Signals
    plt.scatter(df.index[df['Signal'] == 0], df['Close'][df['Signal'] == 0], label ='Sell'\
                , marker='v', color="red", s=100)


    plt.title(f"{ticker} - Moving Average Crossover Signals")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid(True)
    plt.show()





def plot_rsi_signals(df, ticker):
    """
    Creates a two-pane chart: 
    Top pane shows the Price and Buy/Sell signals.
    Bottom pane shows the RSI oscillator with 70/30 thresholds.
    """
    # Create a figure with 2 subplots. The top one (price) gets 70% of the height.
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
    fig.suptitle(f"{ticker} - Pure RSI Strategy", fontsize=16, fontweight='bold')

    # --- TOP PANE: Price & Signals ---
    ax1.plot(df.index, df['Close'], label='Close Price', color='black', alpha=0.6)
    
    # Identify where the bot bought and sold
    buy_signals = df[(df['Signal'] == 1) & (df['Signal'].shift(1) != 1)]
    sell_signals = df[(df['Signal'] == 0) & (df['Signal'].shift(1) == 1)]
    
    # Plot the Buy (Green Up-Arrow) and Sell (Red Down-Arrow) markers
    ax1.scatter(buy_signals.index, buy_signals['Close'], marker='^', color='green', label='Buy Signal', s=100, zorder=3)
    ax1.scatter(sell_signals.index, sell_signals['Close'], marker='v', color='red', label='Sell Signal', s=100, zorder=3)
    
    ax1.set_ylabel("Price ($)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    # --- BOTTOM PANE: The RSI Indicator ---
    ax2.plot(df.index, df['RSI'], label='RSI (14)', color='purple')
    
    # Draw the Overbought (70) and Oversold (30) threshold lines
    ax2.axhline(70, color='red', linestyle='--', alpha=0.5, label='Overbought (70)')
    ax2.axhline(30, color='green', linestyle='--', alpha=0.5, label='Oversold (30)')
    
    # Shade the "Danger Zones" for visual clarity
    ax2.fill_between(df.index, y1=70, y2=100, color='red', alpha=0.1)
    ax2.fill_between(df.index, y1=0, y2=30, color='green', alpha=0.1)
    
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)

    # Clean up the layout and display
    plt.tight_layout()
    plt.show()


# This is the "Combo" strategy visualizer that shows Price, MAs, RSI, and Equity curve all in one unified dashboard.
def plot_combo_signals(df, ticker):
    """
    Unified 3-pane visualizer for the Combo Strategy:
    1. Top: Price, MAs, and Buy/Sell markers.
    2. Middle: RSI with oversold/overbought zones.
    3. Bottom: Portfolio Equity curve to see gains/drawdowns.
    """
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), 
                                         gridspec_kw={'height_ratios': [3, 1, 1]}, 
                                         sharex=True)
    
    fig.suptitle(f"Strategy Deep Dive: {ticker}", fontsize=18, fontweight='bold')

    # --- TOP: Price & Trend Filter (MAs) ---
    ax1.plot(df.index, df['Close'], label='Close Price', color='black', alpha=0.4)
    if 'MA_short' in df.columns:
        ax1.plot(df.index, df['MA_short'], label='Short MA', color='blue', alpha=0.7)
    if 'MA_long' in df.columns:
        ax1.plot(df.index, df['MA_long'], label='Long MA', color='red', alpha=0.7)
    
    # Markers for entries and exits
    buys = df[(df['Signal'] == 1) & (df['Signal'].shift(1) != 1)]
    sells = df[(df['Signal'] == 0) & (df['Signal'].shift(1) == 1)]
    ax1.scatter(buys.index, buys['Close'], marker='^', color='green', s=120, label='Combo Entry', zorder=5)
    ax1.scatter(sells.index, sells['Close'], marker='v', color='red', s=120, label='Combo Exit', zorder=5)
    
    ax1.set_ylabel("Price ($)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.2)

    # --- MIDDLE: RSI Timing ---
    ax2.plot(df.index, df['RSI'], color='purple', label='RSI')
    ax2.axhline(70, color='red', linestyle='--', alpha=0.3)
    ax2.axhline(30, color='green', linestyle='--', alpha=0.3)
    ax2.fill_between(df.index, 70, 100, color='red', alpha=0.05)
    ax2.fill_between(df.index, 0, 30, color='green', alpha=0.05)
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)

    # --- BOTTOM: Performance (Equity Curve) ---
    if 'Equity' in df.columns:
        ax3.plot(df.index, df['Equity'], color='darkgreen', label='Strategy Equity')
        ax3.fill_between(df.index, df['Equity'], color='green', alpha=0.1)
        ax3.set_ylabel("Portfolio Value ($)")
        ax3.set_xlabel("Date")
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()