import json
import os
import sys
from datetime import timedelta
from time import sleep

import schedule
from  timeloop import Timeloop

from chart import TechnicalChart
from gmo.gmo import GMO
from gmocoin_bot.bot import GMOCoinBot, EBotState
from gmocoin_bot.simulator import GMOCoinBotSimulator
from gmocoin_bot.ws import GMOWebsocketManager

bots: list[GMOCoinBot]
tl = Timeloop()

@tl.job(interval=timedelta(minutes=1))
def check_server_status():
    if not SIMULATION_FLG:
        for bot in bots:
            if bot.get_state() == EBotState.Running and bot.get_server_status() != 'OPEN':
                bot.pause()
            elif bot.get_state() == EBotState.Paused and bot.get_server_status() == 'OPEN':
                bot.run()

@tl.job(interval=timedelta(minutes=1))
def monitoring():
    chart.print_candles_by_index(-20)
    print("RSI:", chart.rsi)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("usage: python main.py <simulation_flag> <config_path>")
        exit(-1)

    # シミュレータをデフォルトに
    SIMULATION_FLG = True
    if sys.argv[1] == '0':
        SIMULATION_FLG = False

    config_path = sys.argv[2]
    if not os.path.exists(config_path):
        print(config_path, "not exist")
        exit(-1)

    config = json.load(open(config_path, 'r'))
    access_key = config['access_key']
    secret_key = config['secret_key']
    api = GMO(access_key, secret_key)
    chart = TechnicalChart()
    bot_configs = config['bot_configs']

    bots = []
    if SIMULATION_FLG:
        print("Bot Simulation Start.")
        bots = [GMOCoinBotSimulator(bc, api, chart) for bc in bot_configs]
    else:
        print("****REAL BOT START*****")
        bots = [GMOCoinBot(bc, api, chart) for bc in bot_configs]

    ws_manager = GMOWebsocketManager(bots, chart, api, sim_flg=SIMULATION_FLG)

    tl.start(block=False)

    try:
        while True:
            wait_time = schedule.idle_seconds()
            if wait_time is None:
                raise Exception("There should be some tasks waiting to execute")
            elif wait_time > 0:
                sleep(wait_time)
            schedule.run_pending()
    except KeyboardInterrupt:
        schedule.clear()
        del ws_manager
        del bots

