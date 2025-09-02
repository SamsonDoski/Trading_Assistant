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
    plt.scatter(df.index[df['Signal'] == -1], df['Close'][df['Signal'] == -1], label ='Sell'\
                , marker='v', color="red", s=100)


    plt.title(f"{ticker} - Moving Average Crossover Signals")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid(True)
    plt.show()
