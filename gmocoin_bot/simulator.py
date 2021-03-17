import random
from os.path import exists

from gmo.gmo import PositionJSONEncoder
from gmocoin_bot.bot import *

class GMOCoinBotSimulator(GMOCoinBot):
    LEVERAGE_RATE = 4
    SAVE_PATH = 'simulator_save.json'
    def __init__(self, config_path):
        self.curr_jpy = 0
        super().__init__(config_path)
        self.init_jpy = int(self._api.account_margin()['actualProfitLoss'])
        self.curr_jpy = self.init_jpy

    def _ws_init(self):
        self._ws_ticker = self._ws_subscribe('ticker')
        self._ws_trades = self._ws_subscribe('trades')

    def _init_position_list(self):
        pass
        # if not exists(self.SAVE_PATH):
        #     return
        #
        # with open(self.SAVE_PATH, 'r') as save_data:
        #     save_json = json.load(save_data)
        #     self._position_list = save_json['positions']
        #     self.profit_sum = save_json['lossGain']

    def __save_data(self):
        data = {
            'positions': json.dumps(self._position_list, cls=PositionJSONEncoder),
            'lossGain': self.profit_sum
        }

        with open(self.SAVE_PATH, 'w') as output:
            json.dump(data, output)

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
        self.__save_data()

    def close_position(self, position:Position):
        self.trade_num += 1
        if position.lossGain >= 0:
            self.win_num += 1

        self.profit_sum += position.lossGain
        self.report(position)
        self.curr_jpy += position.lossGain + (position.price * position.size) / position.leverage
        self._position_list.remove(position)
        self._prev_entry_time = None
        self.__save_data()

    def close_positions(self, p_type):
        for p in [p for p in self._position_list if p.type == p_type]:
            self.close_position(p)

    def get_balance(self):
        position_sum = 0
        for p in self._position_list:
            position_sum += p.lossGain + p.price * p.size / p.leverage

        return position_sum + self.curr_jpy




