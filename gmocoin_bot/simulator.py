import random
from gmocoin_bot.bot import *

class GMOCoinBotSimulator(GMOCoinBot):
    LEVERAGE_RATE = 4
    SAVE_PATH = 'simulator_save.json'
    def __init__(self, config_path, api, chart):
        super().__init__(config_path, api, chart)
        self.curr_jpy = self._analyzer.init_jpy

    def _setup_timer(self):
        pass

    def _init_position_list(self):
        pass

    def entry_position(self, side, price, size):
        p = Position({
            'positionId': random.randint(100000, 999999),
            'symbol': self._symbol,
            'price': price,
            'side': side,
            'size': size,
            'orderdSize': "0",
            "lossGain": "0",
            "leverage": LEVERAGE_RATE,
            "losscutPrice": "0",
            'timestamp': datetime.now()
        })

        if self.curr_jpy < p.size * p.price / LEVERAGE_RATE:
            return

        self._position_list.append(p)
        self.curr_jpy -= (p.price * p.size) / LEVERAGE_RATE
        p.entry_report()
        self._prev_entry_time = datetime.now()

    def close_position(self, position:Position):
        self._analyzer.update(position)
        self.report(position)
        self.curr_jpy += position.lossGain + (position.price * position.size) / position.leverage
        self._position_list.remove(position)
        self._prev_entry_time = None

    def close_positions(self, p_type):
        for p in [p for p in self._position_list if p.type == p_type]:
            self.close_position(p)

    def get_balance(self):
        position_sum = 0
        for p in self._position_list:
            position_sum += p.lossGain + p.price * p.size / p.leverage

        return position_sum + self.curr_jpy




