import asyncio
import json

import schedule
from gmo import gmo
from datetime import datetime

class AutoBuyer:
    def __init__(self, config_path):
        config = json.load(open(config_path, 'r'))

        access_key = config['access_key']
        secret_key = config['secret_key']
        self._time_unit = config['time_unit']
        self._frequency = int(config['frequency'])
        self.__gmo = gmo.GMO(access_key, secret_key)
        self._trade_setting_path = config['settings']

    def buy(self):
        print("==================================================")
        print(datetime.now())
        trades = json.load(open(self._trade_setting_path))

        for t in trades:
            symbol = t['symbol']
            size = t['size']
            balance = self.__gmo.account_margin()['availableAmount']
            price = self.__gmo.tickcer(symbol)[0]['ask']
            if balance < size * price:
                continue

            self.__gmo.order(symbol, 'BUY', 'LIMIT', size, price, time_in_force='SOK', cancel_before=True)
            print("BUY {} * {}".format(symbol, size))

        # TODO 成約イベントを監視、成約したら平均レート計算
        print("==================================================")

    async def run(self):
        self.buy()
        if self._time_unit == 'hours':
            schedule.every(self._frequency).hours.do(self.buy)
        elif self._time_unit == 'minutes':
            schedule.every(self._frequency).minutes.do(self.buy)
        elif self._time_unit == 'day':
            schedule.every(self._frequency).days.do(self.buy)

        while True:
            schedule.run_pending()
            await asyncio.sleep(0)

if __name__ == '__main__':
    buyer = AutoBuyer('configs/tsumitate.json')
    asyncio.run(buyer.run())
