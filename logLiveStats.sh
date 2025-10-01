#!/bin/bash

here="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source ~/vRMS/bin/activate
cd $here
python -c "from sendToMQTT import sendStarCountToMqtt;sendStarCountToMqtt()"
python -c "from sendToMQTT import sendLiveMeteorCount;sendLiveMeteorCount()"
python -c "from sendToMQTT import sendOtherData;sendOtherData()"
