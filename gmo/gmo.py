import _thread
import hashlib
import hmac
import json
from datetime import datetime, timedelta
import time
from json import JSONEncoder

import pandas as pd
import requests
import websocket

class CallLimiter:
    def __init__(self, limit=3):
        self.prev_call_time = datetime.now()
        self.call_times = 0
        self.max_call_times = limit

    def enabled_call(self):
        if self.call_times < self.max_call_times:
            return True

        if (datetime.now() - self.prev_call_time).total_seconds() > 1.0:
            self.call_times = 0
            return True

        return False

    def increase_call(self):
        self.call_times += 1
        self.prev_call_time = datetime.now()

    def reset(self):
        self.call_times = 0
        self.prev_call_time = None

class GMO:
    def __init__(self, api_key=None, secret_key=None):
        self._public = 'https://api.coin.z.com/public'
        self.__api_key = api_key
        self.__secret_key = secret_key
        self.__get_limiter = CallLimiter()
        self.__post_limiter = CallLimiter()
        websocket.enableTrace(False)

    def _send_public(self, path):
        response = requests.get(self._public + path).json()
        if response['status'] == 0:
            return response['data']
        else:
            raise Exception("Request Failed")

    def _create_sign(self, text):
        return hmac.new(bytes(self.__secret_key.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()

    def _headers_for_private(self, timestamp, sign):
        return {
            "API-KEY": self.__api_key,
            "API-TIMESTAMP": timestamp,
            "API-SIGN": sign
        }

    def _send_private_get(self, path, parameters={}):
        if not self.__get_limiter.enabled_call():
            time.sleep(1)
            self.__get_limiter.reset()

        timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
        method = 'GET'
        end_point = 'https://api.coin.z.com/private'

        text = timestamp + method + path
        sign = self._create_sign(text)
        headers = self._headers_for_private(timestamp, sign)

        res = requests.get(end_point + path, headers=headers, params=parameters).json()
        self.__get_limiter.increase_call()
        if res['status'] == 0:
            return res['data']
        else:
            raise Exception('Request Failed with status {}'.format(res['status']))

    def _send_private_post(self, path, req_body={}):
        if not self.__post_limiter.enabled_call():
            time.sleep(1)
            self.__post_limiter.reset()

        timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
        method = 'POST'
        end_point = 'https://api.coin.z.com/private'

        text = timestamp + method + path + json.dumps(req_body)
        sign = self._create_sign(text)
        headers = self._headers_for_private(timestamp, sign)

        res = requests.post(end_point + path, headers=headers, data=json.dumps(req_body)).json()
        self.__post_limiter.increase_call()
        if res['status'] == 0:
            if 'data' in res:
                return res['data']
            else:
                return True
        else:
            print(res['message']['message_code'], res['message']['message_string'])
            return False

    def account_margin(self):
        return self._send_private_get('/v1/account/margin')

    def account_assets(self):
        return self._send_private_get('/v1/account/assets')

    def orders(self, orderIds: list):
        return self._send_private_get('/v1/orders', parameters={"orderId": ",".join(orderIds)})

    def cancel_order(self, order_id: int):
        return self._send_private_post('/v1/cancelOrder', req_body={"orderId":order_id})

    def cancel_orders(self, order_ids: list):
        return self._send_private_post('/v1/cancelOrders', req_body={"orderIds": order_ids})

    def activeOrders(self, symbol, page=1, count=100):
        return self._send_private_get('/v1/activeOrders', parameters={"symbol": symbol, "page": page, "count": count})

    def order_by_jpy(self, symbol, side, jpy_price, time_in_force=None, losscut_price=None):
        if side == 'BUY':
            curr_price = float(self.tickcer(symbol)[0]['bid'])
        elif side == 'SELL':
            curr_price = float(self.tickcer(symbol)[0]['ask'])
        else:
            return

        size = "{}".format(jpy_price / curr_price)
        if curr_price > 1000:
            curr_price = "{:.0f}".format(curr_price)
        else:
            curr_price = "{:.3f}".format(curr_price)

        self.order(symbol, side, 'LIMIT', size, curr_price, time_in_force, losscut_price)


    def order(self, symbol, side, execution_type, size, price, time_in_force=None, losscut_price=None,
              cancel_before=None):
        path = '/v1/order'
        req_body = {
            "symbol": symbol,
            "side": side,
            "executionType": execution_type,
            "size": str(size)
        }

        if time_in_force is not None:
            req_body['timeInForce'] = time_in_force
        if symbol in ['BTC_JPY', 'ETH_JPY', 'BCH_JPY', 'LTC_JPY', 'XRP_JPY'] and losscut_price is not None:
            req_body['losscutPrice'] = str(losscut_price)
        if execution_type in ['LIMIT', 'STOP']:
            req_body['price'] = str(price)
        if cancel_before is not None:
            req_body['cancelBefore'] = cancel_before

        return self._send_private_post(path, req_body)

    def executions(self, orderId=None, executionId=None):
        if orderId is not None:
            return self._send_private_get('/v1/executions', parameters={'orderId': orderId})

        if executionId is not None:
            return self._send_private_get('/v1/executions', parameters={'executionId': executionId})

    def get_positions(self, symbol, page=1, count=100):
        return self._send_private_get('/v1/openPositions', parameters={'symbol': symbol, 'page': page, 'count': count})

    def get_position_summary(self, symbol):
        return self._send_private_get('/v1/positionSummary', parameters={'symbol': symbol})

    def get_ws_access_token(self) -> str :
        return self._send_private_post('/v1/ws-auth')

    def extend_ws_access_token(self, token):
        timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
        method = 'PUT'
        end_point = 'https://api.coin.z.com/private'
        path = '/v1/ws-auth'
        req_body = {
            "token": token
        }

        text = timestamp + method + path
        sign = self._create_sign(text)
        headers = self._headers_for_private(timestamp, sign)

        res = requests.put(end_point + path, headers=headers, data=json.dumps(req_body)).json()
        if res['status'] == 0:
            return True
        else:
            raise Exception('Request Failed with status {}'.format(res['status']))

    def delete_ws_access_token(self, token):
        timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
        method = 'DELETE'
        end_point = 'https://api.coin.z.com/private'
        path = '/v1/ws-auth'
        req_body = {
            "token": token
        }

        text = timestamp + method + path
        sign = self._create_sign(text)
        headers = self._headers_for_private(timestamp, sign)

        res = requests.delete(end_point + path, headers=headers, data=json.dumps(req_body)).json()
        if res['status'] == 0:
            return True
        else:
            raise Exception('Request Failed with status {}'.format(res['status']))

    def close_order(self, symbol, side, execution_type, position_id, position_size, price, time_in_force=None, cancel_before=None):
        """
        決済注文
        :param symbol: 銘柄
        :param side: 売買区分
        :param execution_type:
        :param position_id:
        :param position_size:
        :param price:
        :param time_in_force:
        :param cancel_before:
        :return:
        """
        path = '/v1/closeOrder'
        req_body = {
            "symbol": symbol,
            "side": side,
            "executionType": execution_type,
            "settlePosition": [
                {
                    "positionId": position_id,
                    "size": str(position_size)
                }
            ]
        }

        if time_in_force is not None:
            req_body['timeInForce'] = time_in_force
        if execution_type in ['LIMIT', 'STOP']:
            assert (price is not None)
            req_body['price'] = str(price)
        if cancel_before is not None:
            req_body['cancelBefore'] = cancel_before

        return self._send_private_post(path, req_body)

    def close_bulk_order(self, symbol, side, execution_type, size, price, time_in_force=None):
        """
        一括決済
        :param symbol:
        :param side:
        :param execution_type:
        :param size:
        :param price:
        :param time_in_force:
        :return:
        """
        path = '/v1/closeBulkOrder'
        req_body = {
            "symbol": symbol,
            "side": side,
            "executionType": execution_type,
            "size": str(size)
        }

        if time_in_force is not None:
            req_body['timeInForce'] = time_in_force
        if execution_type in ['LIMIT', 'STOP']:
            assert (price is not None)
            req_body['price'] = str(price)

        return self._send_private_post(path, req_body)

    # region public api
    def tickcer(self, symbol):
        return self._send_public('/v1/ticker?symbol={}'.format(symbol))

    def orderbooks(self, symbol):
        """

        :param symbol: BTC|ETH|BCH|LTC|XRP|BTC_JPY|ETH_JPY|BCH_JPY|LTC_JPY|XRP_JPY
        :return:
        """
        return self._send_public('/v1/orderbooks?symbol={}'.format(symbol))

    def trades(self, symbol, page=1, count=100):
        return self._send_public('/v1/trades?symbol={}&page={}&count={}'.format(symbol, page, count))

    def status(self):
        return self._send_public('/v1/status')


    # endregion public api
    # region websockets
    def subscribe_public_ws(self, channel, symbol, on_message):
        entry_point = 'wss://api.coin.z.com/ws/public/v1'
        ws = websocket.WebSocketApp(entry_point,
                                    on_open=lambda wws: wws.send(json.dumps({
                                        "command": "subscribe",
                                        "channel": channel,
                                        "symbol": symbol})
                                    ),
                                    on_message=on_message
                                    )
        _thread.start_new_thread(lambda: ws.run_forever(), ())
        return ws

    def subscribe_private_ws(self, token, channel, on_message) -> websocket.WebSocketApp:
        entry_point = 'wss://api.coin.z.com/ws/private/v1/' + token
        ws = websocket.WebSocketApp(entry_point,
                                    on_open=lambda wws: wws.send(json.dumps({
                                        "command": "subscribe",
                                        "channel": channel})
                                    ),
                                    on_message=on_message
                                    )
        _thread.start_new_thread(lambda: ws.run_forever(), ())
        return ws

class Position:
    def __init__(self, raw_data):
        self.raw = raw_data
        self.id = raw_data['positionId']
        self.symbol = raw_data['symbol']
        self.side = raw_data['side']
        self.size = float(raw_data['size'])
        self.orderdSize = float(raw_data['orderdSize'])
        self.price = float(raw_data['price'])
        self.lossGain = float(raw_data['lossGain'])
        self.leverage = int(raw_data['leverage'])
        self.timestamp = pd.to_datetime(raw_data['timestamp'])

class PositionJSONEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


