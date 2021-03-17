import itertools
import json
import pandas as pd

import websocket

class TechnicalChart:
    def __init__(self, candle_period='T', max_length=3600):
        self.avg_candles = {}
        self.__period = candle_period
        self._max_length = max_length

    def update(self, trade_data):
        now = pd.to_datetime(trade_data['timestamp'])
        now_minute = now.round(self.__period)

        if self.avg_candles.get(now_minute):
            self.avg_candles.get(now_minute).update(trade_data)
        else:
            if len(self.avg_candles) <= 1:  # 始値のずれを修正するため 2分まで普通のローソク足
                self.avg_candles[now_minute] = Candle(trade_data['price'])
            else:
                prev_candle = self.avg_candles[list(self.avg_candles)[-1]]
                self.avg_candles[now_minute] = AverageCandle(prev_candle)

        if len(self.avg_candles) > self._max_length:
            self.avg_candles.pop(list(self.avg_candles)[0])


    def print_candles(self, from_time, to_time):
        c_list = self.get_candles(from_time, to_time)
        result_str = ""
        for c in c_list.values():
            if c.is_up():
                char = '↑'
            else:
                char = '↓'
            result_str += char

        print(result_str)

    def evaluate_candles(self, from_time, to_time):
        c_list = self.get_candles(from_time, to_time)
        return len([c for c in c_list.values() if c.is_up()]) - len([c for c in c_list.values() if c.is_down()])


    def get_candles(self, from_time, to_time):
        f = pd.to_datetime(from_time).round(self.__period)
        t = pd.to_datetime(to_time).round(self.__period)
        f_i = list(self.avg_candles).index(f)
        t_i = list(self.avg_candles).index(t)
        ret = {}
        for i in itertools.islice(list(self.avg_candles), f_i, t_i + 1):
            ret[i] = self.avg_candles[i]

        return ret

    def get_candles_by_index(self, from_index, to_index=-1):
        return self.get_candles(list(self.avg_candles)[from_index], list(self.avg_candles)[to_index])

    def getRSI(self, period=14):
        if len(self.avg_candles) < period:
            return -1

        candles = self.get_candles_by_index(-period)
        if len(candles) < period:
            return -1

        gain_avg = sum([c.close - c.open for c in candles.values() if c.is_up()]) / period
        loss_avg = sum([c.open - c.close for c in candles.values() if c.is_down()]) / period
        rsi = gain_avg / (gain_avg + loss_avg) * 100
        return rsi

class Candle:
    def __init__(self, open_price):
        price = int(open_price)
        self.open = price
        self.high = price
        self.low = price
        self.close = price

    def update(self, tick):
        price = int(tick['price'])
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def __str__(self):
        return "O[{}] H[{}] L[{}] C[{}]".format(self.open, self.high, self.low, self.close)

    def is_up(self):
        return self.close > self.open

    def is_down(self):
        return self.close < self.open

class AverageCandle(Candle):
    """
    平均足
    """

    def __init__(self, prev_candle: Candle):
        super().__init__((prev_candle.open + prev_candle.close) / 2)

    def update(self, tick):
        price = int(tick['price'])
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = (self.high + self.low + self.open + self.close) / 4


if __name__ == '__main__':
    chart = TechnicalChart('T')

    def on_message(ws, message):
        chart.update(json.loads(message))
        print(list(chart.avg_candles)[-1], chart.avg_candles[list(chart.avg_candles)[-1]])


    def on_error(ws, e):
        """

        :type e: Exception
        """
        print(e)


    ws = websocket.WebSocketApp('wss://api.coin.z.com/ws/public/v1',
                                on_open=lambda ws: ws.send(json.dumps({
                                    "command": "subscribe",
                                    "channel": "trades",
                                    "symbol": 'BTC_JPY'})),
                                on_message=on_message,
                                on_error=on_error
                                )
    ws.run_forever()
