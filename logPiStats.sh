#!/bin/bash

here="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source ~/vRMS/bin/activate

cd $here

tm=$(vcgencmd measure_temp | cut -d= -f2)
ds=$(df -h . | tail -1 | awk -F" " '{print $5 }')

python -c "from sendToMQTT import sendOtherData ; sendOtherData(\"${tm}\",\"${ds}\") ; "
