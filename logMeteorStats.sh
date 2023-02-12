#!/bin/bash

here="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source ~/vRMS/bin/activate

python $here/sendToMQTT.py
