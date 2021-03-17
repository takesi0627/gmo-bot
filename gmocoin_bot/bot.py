from datetime import datetime
from enum import Enum
from time import sleep
from typing import List

from chart import ETrendType
from chart.trend import SimpleTrendChecker, RSITrendChecker
from gmo import gmo
from timeloop import Timeloop

from chart.chart import *

"""
1. 利確設定（profit_rate）に上回る時にbest ask/bid で指値決済
2. 最大保有時間（max_keep_time）を上回る且つ損切り設定（loss_cut_rate）下回る時決済
3. 時間間隔毎に保有ポジションの数を確認し、最大保有数以下であればトレンドを判断し、best_ask で購入/best_bidで売り注文を出す
"""

WEBSOCKET_CALL_WAIT_TIME = 3
ORDER_LIMIT_TIME = 60

POSITION_TYPE_BUY = 'BUY'
POSITION_TYPE_SELL = 'SELL'
LEVERAGE_RATE = 4

tl = Timeloop()

class Position(gmo.Position):
    def __init__(self, raw_data):
        super().__init__(raw_data)
        self.size = float(raw_data['size'])
        self.type = raw_data['side']
        self.curr_price = self.price
        self.profit_rate = 0

    def update(self, ticker):

        if self.type == POSITION_TYPE_BUY:
            self.curr_price = int(ticker['last'])

            self.profit_rate = (self.curr_price - self.price) / self.price
            self.lossGain = (self.curr_price - self.price) * self.size
        elif self.type == POSITION_TYPE_SELL:
            self.curr_price = int(ticker['last'])

            self.profit_rate = (self.price - self.curr_price) / self.price
            self.lossGain = (self.price - self.curr_price) * self.size

    def get_keep_time(self):
        now = datetime.now(tz=self.timestamp.tzinfo)
        entry_time = self.timestamp
        return now - entry_time

    def execute_report(self):
        keep_time = self.get_keep_time()
        if self.type == POSITION_TYPE_BUY:
            return str.format("[BUY: {:.0f} -> SELL: {:.0f}][KEEP TIME: {}] 損益：{:+.0f}",
                              self.price, self.curr_price, keep_time, self.lossGain)
        elif self.type == POSITION_TYPE_SELL:
            return str.format("[SELL: {:.0f} -> BUY: {:.0f}][KEEP TIME: {}] 損益：{:+.0f}",
                              self.price, self.curr_price, keep_time, self.lossGain)

    def entry_report(self):
        print("POSITION ENTRY： type[{}] price[{}] size[{}]".format(self.side, self.price, self.size))

class BotParams:
    def __init__(self, bot_config):
        self.profit_rate = bot_config['profit_rate']
        self.loss_cut_rate = bot_config['loss_cut_rate']
        self.max_positions = bot_config['max_positions']
        self.position_unit = bot_config['position_unit']
        self.max_keep_time = bot_config['max_keep_time']
        self.gate_time = bot_config['gate_time']
        self.second_profit_rate = bot_config['second_profit_rate']
        self.entry_cool_time = bot_config['entry_cool_time']

class EBotState(Enum):
    Initializing = 0
    Initialized = 1
    Running = 2
    Paused = 3

class GMOCoinBot:
    _position_list: List[Position]
    _ws_ticker: websocket.WebSocketApp
    _ws_trades: websocket.WebSocketApp
    _ws_execution_events: websocket.WebSocketApp
    _ws_order_events: websocket.WebSocketApp
    _ws_position_events: websocket.WebSocketApp
    _prev_entry_time: datetime = None
    _entry_order_list: List[int]
    _state = EBotState

    def __init__(self, config_path):
        self.__set_state(EBotState.Initializing)
        config = json.load(open(config_path, 'r'))
        access_key = config['access_key']
        secret_key = config['secret_key']
        bot_config = config['bot_configs']

        # 分平均足のチャートを作成
        self.chart = TechnicalChart('T')
        self.trend_checker = SimpleTrendChecker()

        # パラメータ初期化
        self._api = gmo.GMO(access_key, secret_key)
        self._symbol = bot_config['symbol']
        self.params = BotParams(bot_config)

        self._entry_order_list = []
        self._position_list = []
        self._prev_entry_time = None
        self.__token = ''

        # 分析用
        self.win_num = 0
        self.trade_num = 0
        self.init_jpy = 0
        self.profit_sum = 0 # 決済済みの利益総和

        self.__set_state(EBotState.Initialized)

        # サーバ状態をチェックしてから起動
        if self.get_server_status() == 'OPEN':
            self.run()
        else:
            self.__set_state(EBotState.Paused)

    def run(self):
        self.init_jpy = self.get_balance()

        # ポジション、注文の初期状態を取得
        self.__init_order_list()
        self._init_position_list()

        # WebSocket購読
        self.__token = self._api.get_ws_access_token()
        print("=============Initialize Websocket ...===============")
        self._ws_init()
        print("============== Websocket initialized ===============")

        self.__set_state(EBotState.Running)

    def _init_position_list(self):
        self._position_list.clear()
        positions = self._api.get_positions(self._symbol)
        if positions:
            for p in positions['list']:
                self._position_list.append(Position(p))

    def get_state(self) -> EBotState:
        return self._state

    def __set_state(self, state: EBotState):
        print("Set Bot State to:", state)
        self._state = state

    def update_positions(self):
        self._init_position_list()

    def __init_order_list(self):
        orders = self._api.activeOrders(self._symbol)
        if orders:
            self._entry_order_list = [int(o['orderId']) for o in orders if o['settleType'] == 'OPEN']
            o_close = [int(o['orderId']) for o in orders if o['settleType'] == 'CLOSE']
            if o_close:
                self._api.cancel_orders(o_close)
                sleep(1) # キャンセルまで時間かかるかもしれない、一応

    def __del__(self):
        if self.get_server_status() == 'OPEN':
            self.__ws_close()
            self._api.delete_ws_access_token(self.__token)

    def get_server_status(self):
        return self._api.status()['status']

    def pause(self):
        self.__set_state(EBotState.Paused)
        self.__ws_close()

    def ws_check_connection(self):
        if not self._ws_ticker.keep_running:
            self._ws_ticker = self._ws_subscribe('ticker')
        if not self._ws_trades.keep_running:
            self._ws_trades = self._ws_subscribe('trades')
        if not self._ws_order_events.keep_running:
            self._ws_execution_events = self._ws_subscribe('executionEvents')
        if not self._ws_position_events.keep_running:
            self._ws_order_events = self._ws_subscribe('orderEvents')
        if not self._ws_execution_events.keep_running:
            self._ws_position_events = self._ws_subscribe('positionEvents')

    def _ws_init(self):
        self._ws_ticker = self._ws_subscribe('ticker')
        self._ws_trades = self._ws_subscribe('trades')
        self._ws_execution_events = self._ws_subscribe('executionEvents')
        self._ws_order_events = self._ws_subscribe('orderEvents')
        self._ws_position_events = self._ws_subscribe('positionEvents')

    def _ws_subscribe(self, channel) -> websocket.WebSocketApp or None:
        ws = None
        if channel == 'ticker':
            ws = self._api.subscribe_public_ws('ticker', self._symbol, lambda ws, message: self.update_ticker(json.loads(message)))
        elif channel == 'trades':
            ws = self._api.subscribe_public_ws('trades', self._symbol, lambda ws, message: self.update_trades(json.loads(message)))
        elif channel == 'executionEvents':
            ws = self._api.subscribe_private_ws(self.__token, 'executionEvents', lambda ws, message: self.on_execution_events(json.loads(message)))
        elif channel == 'orderEvents':
            ws = self._api.subscribe_private_ws(self.__token, 'orderEvents', lambda ws, message: self.on_order_events(json.loads(message)))
        elif channel == 'positionEvents':
            ws = self._api.subscribe_private_ws(self.__token, 'positionEvents', lambda ws, message: self.on_position_events(json.loads(message)))
        else:
            return None

        sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        return ws

    def __ws_close(self):
        if self._ws_ticker and self._ws_ticker.keep_running:
            self._ws_ticker.send(json.dumps({"command": "unsubscribe", "channel": "ticker", "symbol": self._symbol}))
            self._ws_ticker.close()
            sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        if self._ws_trades and self._ws_trades.keep_running:
            self._ws_trades.send(json.dumps({"command": "unsubscribe", "channel": "trades", "symbol": self._symbol}))
            self._ws_trades.close()
            sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        if  self._ws_execution_events and self._ws_execution_events.keep_running:
            self._ws_execution_events.send(json.dumps({"command": "unsubscribe", "channel": "executionEvents"}))
            self._ws_execution_events.close()
            sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        if self._ws_order_events and self._ws_order_events.keep_running:
            self._ws_order_events.send(json.dumps({"command": "unsubscribe", "channel": "orderEvents"}))
            self._ws_order_events.close()
            sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        if self._ws_position_events and self._ws_position_events.keep_running:
            self._ws_position_events.send(json.dumps({"command": "unsubscribe", "channel": "positionEvents"}))
            self._ws_position_events.close()
            sleep(WEBSOCKET_CALL_WAIT_TIME)

    def extend_token(self):
        self._api.extend_ws_access_token(self.__token)
        print("EXTEND TOKEN")

    def on_execution_events(self, execution_data):
        settle_type = execution_data['settleType']
        order_id = int(execution_data['orderId'])
        if settle_type == 'OPEN':
            if order_id in self._entry_order_list:
                self._entry_order_list.remove(order_id)
        elif settle_type == 'CLOSE':
            lossGain = int(execution_data['lossGain'])
            if lossGain > 0:
                self.win_num += 1
            self.trade_num += 1
            self.profit_sum += lossGain
            close_pos = self.get_position(execution_data['positionId'])
            if close_pos:
                self._position_list.remove(close_pos)
                close_pos.lossGain = lossGain
                self.report(close_pos)

            self._prev_entry_time = None

    def on_order_events(self, order_data):
        order_id = int(order_data['orderId'])
        message_type = order_data['msgType']
        if message_type == 'NOR': # 新規注文　
            if order_data['settleType'] == 'OPEN':
                self._entry_order_list.append(order_id)
        else: # キャンセル等
            if order_data['settleType'] == 'OPEN':
                self._entry_order_list.remove(order_id)

    def on_position_events(self, position_data):
        msg_type = position_data['msgType']
        if msg_type == 'OPR': # ポジションオープン
            self._position_list.append(Position(position_data))
            # self._position_list[-1].entry_report()
            self._prev_entry_time = datetime.now()
        elif msg_type == 'UPR': # 部分決済
            update_pos = self.get_position(position_data['positionId'])
            if update_pos:
                update_pos.size = int(position_data['size'])

    def get_position(self, p_id):
        return next(p for p in self._position_list if p.id == int(p_id))

    def update_ticker(self, ticker):
        # ここでポジションの決済、エントリを決める
        # ポジションの更新
        for p in self._position_list:
            p.update(ticker)
            if self.should_exit(p):
                self.close_position(p)

        trend = self.trend_checker.check_trend(self.chart)
        if trend == ETrendType.UP:
            if self.can_entry():
                self.entry_position(POSITION_TYPE_BUY, ticker['ask'], self.params.position_unit)
            self.close_positions(POSITION_TYPE_SELL)
        elif trend == ETrendType.DOWN:
            if self.can_entry():
                self.entry_position(POSITION_TYPE_SELL, ticker['bid'], self.params.position_unit)
            self.close_positions(POSITION_TYPE_BUY)

    def update_trades(self, trade):
        self.chart.update(trade)

    def is_position_timeout(self, position: Position):
        keep_time_sec = position.get_keep_time().seconds
        if keep_time_sec > self.params.max_keep_time:
            print(keep_time_sec, position.timestamp)
        return keep_time_sec > self.params.max_keep_time

    def should_exit(self, position: Position):
        if position.profit_rate > self.params.profit_rate:
            return True

        # if self.is_position_timeout(position):
        #     # self.chart.print_candles(position.timestamp, datetime.now(tz=position.timestamp.tzinfo))
        #     return True
        #
        # if position.get_keep_time().seconds > self.params.gate_time:
        #     return position.profit_rate > self.params.second_profit_rate

        return False

    def entry_position(self, side, price, size):
        self._prev_entry_time = datetime.now()

        margin = int(self._api.account_margin()['availableAmount'])
        if margin < float(price) * size / float(LEVERAGE_RATE):
            return

        self._api.order(self._symbol, side, 'LIMIT', size, int(price))

    def close_position(self, position:Position):
        if position.type == POSITION_TYPE_BUY:
            self._api.close_order(self._symbol, POSITION_TYPE_SELL, 'LIMIT', position.id, position.size, position.curr_price, time_in_force='FOK')
        elif position.type == POSITION_TYPE_SELL:
            self._api.close_order(self._symbol, POSITION_TYPE_BUY, 'LIMIT', position.id, position.size, position.curr_price, time_in_force='FOK')

    def close_positions(self, p_type):
        p_list = [p for p in self._position_list if p.type == p_type]
        if p_list:
            p_size = sum([p.size for p in p_list])
            price = p_list[0].curr_price
            if p_type == POSITION_TYPE_BUY:
                self._api.close_bulk_order(self._symbol, POSITION_TYPE_SELL, 'LIMIT', p_size, price, time_in_force='FOK')
            elif p_type == POSITION_TYPE_SELL:
                self._api.close_bulk_order(self._symbol, POSITION_TYPE_BUY, 'LIMIT', p_size, price, time_in_force='FOK')

    def cancel_order_check(self):
        cancel_ids = []
        active_orders = self._api.activeOrders('BTC_JPY')
        if active_orders:
            # 決済中の注文をキャンセル
            executing_orders = [o for o in active_orders['list'] if o['settleType'] == 'CLOSE']
            for o in executing_orders:
                order_time = pd.to_datetime(o['timestamp'])
                now = datetime.now(tz=order_time.tzinfo)
                if (now - order_time).seconds > ORDER_LIMIT_TIME:
                    cancel_ids.append(o['orderId'])

        if self._entry_order_list:
            # 発注中の注文をキャンセル
            order_ids = [str(ID) for ID in self._entry_order_list][0:10]
            orders = self._api.orders(order_ids)
            if not orders:
                return

            for o in orders['list']:
                # 有効以外の場合はスルー
                if o['status'] != 'ORDERED':
                    continue

                order_time = pd.to_datetime(o['timestamp'])
                now = datetime.now(tz=order_time.tzinfo)
                if (now - order_time).seconds > ORDER_LIMIT_TIME:
                    cancel_ids.append(o['orderId'])

        if len(cancel_ids) > 0:
            self._api.cancel_orders(cancel_ids)

    def can_entry(self):
        # クールタイム中
        now = datetime.now()
        if self._prev_entry_time is not None and (now - self._prev_entry_time).seconds < self.params.entry_cool_time:
            return False

        # ポジション最大数超えてる
        if (len(self._entry_order_list) + len(self._position_list)) >= self.params.max_positions:
            return False

        return True

    def get_balance(self):
        """
        含み損益を含めた現在の残高
        :return:
        """
        return int(self._api.account_margin()['actualProfitLoss'])

    def get_profit_rate(self):
        return self.profit_sum / self.init_jpy

    def report(self, p: Position):
        print("[{}]決済しました。{} 勝率[{:.2%}] 時価評価総額: {:.0f} 利回り[{:+.0f} {:.2%}]".format(
            datetime.now(), p.execute_report(), self.win_num / self.trade_num, self.get_balance(), self.profit_sum, self.get_profit_rate()
        ))
