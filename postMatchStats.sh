#!/bin/bash
# Copyright (C) Mark McIntyre
#
# clear down anything older than 20 days from ArchivedFiles

here="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source ~/vRMS/bin/activate
cd $here
statid=$1
if [ "$statid" == "" ] ; then 
    python -c "from sendToMQTT import sendMatchdataToMqtt;sendMatchdataToMqtt();"
    python -c "from sendToMQTT import sendToMqtt;sendToMqtt();"
else
    python -c "from sendToMQTT import sendMatchdataToMqtt;sendMatchdataToMqtt('$statid');"
    python -c "from sendToMQTT import sendToMqtt;sendToMqtt('$statid');"
fi 
