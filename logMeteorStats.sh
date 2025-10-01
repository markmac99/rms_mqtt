#!/bin/bash

here="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source ~/vRMS/bin/activate
cd $here
python -c "from sendToMQTT import sendToMqtt;sendToMqtt(statid='$1')"
