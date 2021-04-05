import asyncio
import json

import schedule
from gmo import gmo
from datetime import datetime

class AutoBuyer:
    SAVE_FILE_PATH = 'save/tsumitate-jpy-used.json'

    def __init__(self, config_path):
        config = json.load(open(config_path, 'r'))

        access_key = config['access_key']
        secret_key = config['secret_key']
        self._time_unit = config['time_unit']
        self._frequency = int(config['frequency'])
        self.__gmo = gmo.GMO(access_key, secret_key)
        self._trade_setting_path = config['settings']

        with open(self.SAVE_FILE_PATH, 'r') as f:
            self.__jpy_used = json.load(f)

    def buy(self):
        print("==================================================")
        print(datetime.now())
        with open(self._trade_setting_path) as f:
            trades = json.load(f)

            for t in trades:
                symbol = t['symbol']
                size = t['size']
                balance = int(self.__gmo.account_margin()['availableAmount'])
                price = float(self.__gmo.tickcer(symbol)[0]['ask'])
                if balance < size * price:
                    continue

                self.__gmo.order(symbol, 'BUY', 'LIMIT', size, price)
                print("BUY {} * {} at rate[{}]".format(symbol, size, price))
                if self.__jpy_used[symbol]:
                    self.__jpy_used[symbol] += int(price * size)
                else:
                    self.__jpy_used[symbol] = int(price * size)

                with open(self.SAVE_FILE_PATH, 'w') as f_save:
                    f_save.write(json.dumps(self.__jpy_used))

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
