def main():

    TICKER = input(str("What stock do you want to check?: ")).upper()
    '''
    from utils.data_loader import fetch_data
    #fetch data with defined parameters
    df = fetch_data("AAPL", start="2022-01-01", end="2025-08-13")
    print(df)
    '''


    from utils.data_loader import fetch_data
    from strategies.moving_average import apply_moving_average_strategy
    from utils.visualize1 import plot_ma_signals as plot
    from engine.backtest import BacktestEngine


    df = fetch_data(TICKER, start="2022-01-01", end="2025-08-14")
    df = apply_moving_average_strategy(df)
    print(df.tail(200))
    # print(df.dtypes)


   
    # Backtesting
    engine = BacktestEngine(initial_equity=10000)
    df_bt = engine.run(df)
    summary = engine.summary(df_bt)

    print(f"Backtest Summary for {TICKER}:")
    for k, v in summary.items():
        print(f"{k}: {v}")

    #plotting signals to visualize
    plot(df, TICKER)


if __name__ == "__main__":
    main()
