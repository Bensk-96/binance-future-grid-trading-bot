from binance.client import Client
import pandas as pd
import requests
from decouple import config
import time

api = config("API")
api_secret = config("API_SECRET")

client = Client(api,api_secret,tld="com",testnet=True)

class Bot:
    def __init__(self,symbol,no_of_decimals,volume,proportion,tp,n):
        self.symbol = symbol
        self.no_of_decimals = no_of_decimals
        self.volume = volume
        self.proportion = proportion
        self.tp = tp
        self.n = n

    def get_balance(self):
        x = client.futures_account()
        df = pd.DataFrame(x['assets'])
        print(df)

    def get_current_price(self,symbol):
        response = requests.get(f'https://testnet.binancefuture.com/fapi/v1/ticker/price?symbol={symbol}')
        price = float(response.json()['price'])
        return price

    def sell_limit(self,symbol, volume, price):
        output = client.futures_create_order(

            symbol=symbol,
            side=Client.SIDE_SELL,
            type=Client.FUTURE_ORDER_TYPE_LIMIT,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=volume,
            price=price,
        )
        print(output)

    def buy_limit(self,symbol, volume, price):
        output = client.futures_create_order(

            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.FUTURE_ORDER_TYPE_LIMIT,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=volume,
            price=price,
        )
        print(output)

    def close_orders(self,symbol):
        x = client.futures_get_open_orders(symbol=symbol)
        df = pd.DataFrame(x)
        for index in df.index:
            client.futures_cancel_order(symbol=symbol, orderId=df["orderId"][index])

    def close_buy_orders(self,symbol):
        x = client.futures_get_open_orders(symbol=symbol)
        df = pd.DataFrame(x)
        df = df[df["side"] == "BUY"]
        for index in df.index:
            client.futures_cancel_order(symbol=symbol, orderId=df["orderId"][index])

    def close_sell_orders(self,symbol):
        x = client.futures_get_open_orders(symbol=symbol)
        df = pd.DataFrame(x)
        df = df[df["side"] == "SELL"]
        for index in df.index:
            client.futures_cancel_order(symbol=symbol, orderId=df["orderId"][index])

    def get_direction(self,symbol):
        x = client.futures_position_information(symbol=symbol)
        df = pd.DataFrame(x)
        if float(df["positionAmt"].sum()) > 0:
            return "LONG"
        if float(df["positionAmt"].sum()) < 0:
            return "SHORT"
        else:
            return "FLAT"

    def get_mark_price(self,symbol):
        x = client.get_symbol_ticker(symbol=symbol)
        price = float(x["price"])
        return price

    def draw_grid(self,n):
        pct_change = 1
        adj_sell = 1.2
        current_price = self.get_mark_price(self.symbol)
        for i in range(n):
            sell_price = float(
                round(((pct_change / 100) * current_price * adj_sell * self.proportion) + current_price, self.no_of_decimals))
            self.sell_limit(self.symbol, self.volume, sell_price)
            pct_change += 1
            adj_sell += 0.2

        pct_change = -1
        adj_buy = 1.2
        current_price = self.get_mark_price(self.symbol)
        for i in range(n):
            buy_price = float(
                round(((pct_change / 100) * current_price * adj_sell * self.proportion) + current_price, self.no_of_decimals))
            self.buy_limit(self.symbol, self.volume, buy_price)
            pct_change -= 1
            adj_buy += 0.2

    def cal_tp_level(self,symbol, tp):
        try:
            x = client.futures_position_information(symbol=symbol)
            df = pd.DataFrame(x)
            df = df.loc[df["positionAmt"] != "0.000"]
            t_margin = (float(df["entryPrice"][0]) * abs(float(df["positionAmt"][0]))) / float(df["leverage"][0])
            profit = float(t_margin * tp * 0.01)
            price = round((profit / float(df["positionAmt"][0])) + float(df["entryPrice"][0]), self.no_of_decimals)
            t_position_amt = 0
            for index in df.index:
                t_position_amt += abs(float(df["positionAmt"][index]))
            return price, t_position_amt

        except:
            pass

    def place_tp_order(self,symbol, price, t_position_amt, direction):
        try:
            if direction == "LONG":
                self.sell_limit(symbol, t_position_amt, price)
            if direction == "SHORT":
                self.buy_limit(symbol, t_position_amt, price)
        except:
            self.place_tp_order(symbol, price, t_position_amt, direction)


    def run(self):
        while True:
            x = client.futures_get_open_orders(symbol=self.symbol)
            df1 = pd.DataFrame(x)
            if len(df1) == 0:
                self.draw_grid(self.n)
            time.sleep(1)  # Sleep after checking open orders

            y = client.futures_position_information(symbol=self.symbol)
            df2 = pd.DataFrame(y)
            df2 = df2.loc[df2["positionAmt"] != "0.000"]
            if len(df2) > 0:
                direction = self.get_direction(self.symbol)
                try:
                    if direction == "LONG":
                        print("close buy")
                        self.close_sell_orders(self.symbol)
                    if direction == "SHORT":
                        print("close sell")
                        self.close_buy_orders(self.symbol)
                except:
                    pass
                time.sleep(1)  # Sleep after closing orders

                price0, amount0 = self.cal_tp_level(self.symbol, self.tp)
                self.place_tp_order(self.symbol, price0, amount0, direction)
                time.sleep(1)  # Sleep after placing TP order

                is_ok = True
                while is_ok:
                    try:
                        price1, amount1 = self.cal_tp_level(self.symbol, self.tp)
                        print(f"price: {price1} amount: {amount1}")
                        if price1 != price0 or amount1 != amount0:
                            if direction == "LONG":
                                self.close_sell_orders(self.symbol)
                            if direction == "SHORT":
                                self.close_buy_orders(self.symbol)
                            self.place_tp_order(self.symbol, price1, amount1, direction)
                            price0 = price1
                            amount0 = amount1
                        time.sleep(1)  # Sleep within loop after placing TP order
                        print("sleep for 1 s")
                    except:
                        pass

                    y = client.futures_position_information(symbol=self.symbol)
                    df2 = pd.DataFrame(y)
                    df2 = df2.loc[df2["positionAmt"] != "0.000"]
                    if len(df2) == 0:
                        try:
                            self.close_orders(self.symbol)
                            is_ok = False
                        except:
                            pass
                    time.sleep(1)  # Sleep after checking position information
                print("sleep for 1 s")

            time.sleep(1)  # Sleep at the end of the while loop
            print("sleep for 1 s")
