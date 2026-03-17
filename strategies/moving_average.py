import numpy as np

# function calculates and adds Moving Averages to all rows(days)
# and indicates buy and sell signals
def apply_moving_average_strategy(df, short_window=50, long_window=200):
    #might change this parameter later to 7 days/30 days/60/120 etc 
    df["MA_short"] = df["Close"].rolling(window=short_window).mean()
    df["MA_long"] = df["Close"].rolling(window=long_window).mean()
    #create column 'signal'
    df["signal"] = 0
    #loc[row,column] pandas function
    df.loc[df["MA_short"] > df["MA_long"], "Signal"] = 1 #Buy
    df.loc[df["MA_short"] < df["MA_long"], "Signal"] = -1 #Sell
    
    return df
