from abc import abstractmethod

from chart import ETrendType
from chart.chart import TechnicalChart


class TrendChecker:
    @abstractmethod
    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        pass

class SimpleTrendChecker2(TrendChecker):
    CHECK_LENGTH = 3
    START_COOL_TIME = 5
    THRESHOLD = 0.001

    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        if len(chart.avg_candles) < self.START_COOL_TIME:
            return ETrendType.NONE

        if len(chart.avg_candles) < self.CHECK_LENGTH:
            return ETrendType.NONE

        candles = chart.get_candles_by_index(-self.CHECK_LENGTH)
        if self.in_up_trend(candles):
            return ETrendType.UP

        if self.in_down_trend(candles):
            return ETrendType.DOWN

        return ETrendType.NONE

    def in_up_trend(self, candles):
        latest = candles[list(candles)[-2]]
        if latest.loss_gain_rate() > self.THRESHOLD:
            return True

        return all([c.is_up() for c in candles.values()])

    def in_down_trend(self, candles):
        latest = candles[list(candles)[-2]]
        if latest.loss_gain_rate() < -self.THRESHOLD:
            return True

        return all([c.is_down() for c in candles.values()])


class SimpleTrendChecker(TrendChecker):
    CHECK_LENGTH = 3
    START_COOL_TIME = 5
    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        if len(chart.avg_candles) < self.START_COOL_TIME:
            return ETrendType.NONE

        if len(chart.avg_candles) < self.CHECK_LENGTH:
            return ETrendType.NONE

        candles = chart.get_candles_by_index(-self.CHECK_LENGTH)
        if self.in_up_trend(candles):
            return ETrendType.UP

        if self.in_down_trend(candles):
            return ETrendType.DOWN

        return ETrendType.NONE

    def in_up_trend(self, candles):
        return all([c.is_up() for c in candles.values()])

    def in_down_trend(self, candles):
        return all([c.is_down() for c in candles.values()])

class RSITrendChecker(SimpleTrendChecker):
    def __init__(self, period=14, th1=40, th2=60):
        super().__init__()
        self._period = period
        self._th1 = th1
        self._th2 = th2

    def check_trend(self, chart: TechnicalChart) -> ETrendType:
        rsi = chart.getRSI(self._period)

        if rsi == -1:
            # return super().check_trend(chart)
            return ETrendType.NONE
        else:
            simple_trend = super().check_trend(chart)
            if simple_trend == ETrendType.UP:
                if rsi < self._th1:
                    return ETrendType.NONE
                else:
                    return ETrendType.UP
            elif simple_trend == ETrendType.DOWN:
                if rsi > self._th2:
                    return ETrendType.NONE
                else:
                    return ETrendType.DOWN

        return ETrendType.NONE
