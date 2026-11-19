# Tests for sendToMQTT
# copyright Mark McIntyre, 2025

from sendToMQTT import sendLastBoot, sendCameraStatus, sendLiveMeteorCount
from sendToMQTT import sendMatchdataToMqtt, sendOtherData, sendStarCountToMqtt


def test_sendLastBoot():
    ret = sendLastBoot('testing')
    assert ret is None


def test_SendOtherData():
    ret = sendOtherData(60, 'testing')
    assert ret is None
