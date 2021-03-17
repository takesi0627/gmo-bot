from abc import abstractmethod

from chart import ETrendType
from chart.chart import TechnicalChart


class TrendChecker:
    @abstractmethod
    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        pass


class SimpleTrendChecker(TrendChecker):
    CHECK_LENGTH = 3

    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        candles = chart.candles
        if len(candles) < self.CHECK_LENGTH:
            return ETrendType.NONE


        if self.in_up_trend(candles):
            return ETrendType.UP

        if self.in_down_trend(candles):
            return ETrendType.DOWN

        return ETrendType.NONE

    def in_up_trend(self, candles):
        for i in range(-3, 0):
            if not candles[list(candles)[i]].is_up():
                return False

        return True

    def in_down_trend(self, candles):
        for i in range(-3, 0):
            if not candles[list(candles)[i]].is_down():
                return False

        return True


class RSITrendChecker(SimpleTrendChecker):
    def __init__(self, period=14):
        super().__init__()
        self._period = period

    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        rsi = chart.getRSI(self._period)

        if rsi == -1:
            # return super().check_trend(chart)
            return ETrendType.NONE
        else:
            simple_trend = super().check_trend(chart)
            if simple_trend == ETrendType.UP:
                if rsi > 50:
                    return ETrendType.UP
                else:
                    return ETrendType.NONE
            elif simple_trend == ETrendType.DOWN:
                if rsi < 50:
                    return ETrendType.DOWN
                else:
                    return ETrendType.NONE

        return ETrendType.NONE
