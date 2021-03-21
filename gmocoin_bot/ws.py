import json
from datetime import datetime
from time import sleep

import schedule as schedule
import websocket

from gmo.gmo import GMO
from gmocoin_bot.bot import GMOCoinBot, EBotState

WEBSOCKET_CALL_WAIT_TIME = 3
CHANNEL_NAME_TICKER = 'ticker'
CHANNEL_NAME_TRADES = 'trades'
CHANNEL_NAME_EXECUTION = 'executionEvents'
CHANNEL_NAME_ORDER = 'orderEvents'
CHANNEL_NAME_POSITION = 'positionEvents'

class GMOWebsocketManager:
    _ws_list: dict[str, websocket.WebSocketApp or None]
    _bots: list[GMOCoinBot]

    def __init__(self, bots, chart, api: GMO, sim_flg=True):
        self._bots = bots
        self._chart = chart
        self._api = api
        self._sim_flg = sim_flg
        self.__token = api.get_ws_access_token()
        self._ws_list = {
            CHANNEL_NAME_TICKER: None,
            CHANNEL_NAME_TRADES: None,
            CHANNEL_NAME_EXECUTION: None,
            CHANNEL_NAME_ORDER: None,
            CHANNEL_NAME_POSITION: None,
        }

        self._connect()
        self.__setup_timer()

    def __del__(self):
        for channel, ws in self._ws_list.items():
            if ws and ws.keep_running:
                if channel in [CHANNEL_NAME_TICKER, CHANNEL_NAME_TRADES]:
                    ws.send(json.dumps({"command": "unsubscribe", "channel": channel, "symbol": 'BTC_JPY'}))
                else:
                    ws.send(json.dumps({"command": "unsubscribe", "channel": channel}))
                ws.close()
                sleep(WEBSOCKET_CALL_WAIT_TIME)

    def __setup_timer(self):
        # 5秒ごとにwebソケットの状態を確認
        schedule.every(5).seconds.do(self._connect)
        # 50分ごとにトークンの延長
        schedule.every(50).minutes.do(self._extend_token)

    def _extend_token(self):
        if self._api.status() != 'OPEN' or not self.__token:
            return

        self._api.extend_ws_access_token(self.__token)
        print("[{}] TOKEN EXTENDED".format(datetime.now()))

    def _connect(self):
        if self._api.status()['status'] != 'OPEN':
            return

        for channel, ws in self._ws_list.items():
            if channel in [CHANNEL_NAME_EXECUTION, CHANNEL_NAME_ORDER, CHANNEL_NAME_POSITION] and self._sim_flg:
                continue

            if not ws or not ws.keep_running:
                try:
                    self._ws_list[channel] = self.__ws_subscribe(channel)
                except TimeoutError or ConnectionError:
                    if self._ws_list[channel] and not self._ws_list[channel].sock.closed():
                        self._ws_list[channel].close()

                    self._ws_list[channel] = None

        for b in [b for b in self._bots if b.get_state() != EBotState.Running]:
            b.run()

    def __ws_subscribe(self, channel) -> websocket.WebSocketApp or None:
        if channel == CHANNEL_NAME_TICKER:
            ws = self._api.subscribe_public_ws(CHANNEL_NAME_TICKER, 'BTC_JPY', lambda _, message: self.__on_ticker(json.loads(message)))
        elif channel == CHANNEL_NAME_TRADES:
            ws = self._api.subscribe_public_ws(CHANNEL_NAME_TRADES, 'BTC_JPY', lambda _, message: self.__update_trades(json.loads(message)))
        elif channel == CHANNEL_NAME_EXECUTION:
            ws = self._api.subscribe_private_ws(self.__token, CHANNEL_NAME_EXECUTION, lambda _, message: self.__on_execution_events(json.loads(message)))
        elif channel == CHANNEL_NAME_ORDER:
            ws = self._api.subscribe_private_ws(self.__token, CHANNEL_NAME_ORDER, lambda _, message: self.__on_order_events(json.loads(message)))
        elif channel == CHANNEL_NAME_POSITION:
            ws = self._api.subscribe_private_ws(self.__token, CHANNEL_NAME_POSITION, lambda _, message: self.__on_position_events(json.loads(message)))
        else:
            return None

        print("[{}] Subscribe [{}]".format(datetime.now(), channel))
        sleep(WEBSOCKET_CALL_WAIT_TIME)  # 一秒間1回しか購読できないため
        return ws

    def __update_trades(self, trade):
        self._chart.update(trade)

    def __on_execution_events(self, data):
        for b in self._bots:
            b.on_execution_events(data)

    def __on_order_events(self, data):
        for b in self._bots:
            b.on_order_events(data)

    def __on_position_events(self, data):
        for b in self._bots:
            b.on_position_events(data)

    def __on_ticker(self, data):
        for b in self._bots:
            b.update_ticker(data)
