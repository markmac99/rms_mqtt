# Monitoring and RMS camera with MQ 

If you are running OpenHAB, Home Assistant or a similar home automation software you can monitor the RMS meteor camera with [MQTT](https://mqtt.org/).  MQTT is a lightweight messaging protocol widely used in the IoT (Internet of Things) world to communicate between smart devices. For example using MQTT your home automation software can monitor and control smart plugs, switches, weatherstations, doorbells and so forth.

## Installation
Note: you must have RMS installed and configured, either in single-cam or multi-cam mode. 

Clone this repository to your Pi or linux RMS box:
``` bash
cd ~/source
git clone https://github.com/markmac99/rms_mqtt
```
Activate the RMS python virtual environment and install the requirements with 
``` bash
pip install -r requirements.txt
```

## Configuration
Copy `config.ini.example` to `config.ini` and update it with the details of your MQ server. At this time, SSL is not supported so CAFILE is not required. 

If you're *not* using a multi-cam setup, update `RMSDIR` with the full path of the folder containing RMS, for example `/home/rms/source/RMS`. 

Add your Camera IDs to the `[stations]` section, as shown below. You can add/remove IDs as needed. 
``` bash
[stations]
ID1=XX0001
ID2=XX0002
```

### Testing
You can test functionality by doing the following in a Terminal window:
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt('testing')"
```
This will publish to a topic `meteorcams/testing`. 

## Usage

There are four functions that can be used to submit meteor-related data to MQ:

* `sendToMqtt` will publish the latest count of detections and meteors. 
* `sendStarCountToMqtt` will publish the latest star count. 
* `sendLiveMeteorCount` will publish a live count of potential detections.  
* `sendMatchdataToMqtt` if you're a UKMON member then this will publish the count of confirmed matches your station was involved in. 

### Example use from the commandline
All functions can be invoked in a similar way to the examples below. 

This invocation will read the station list from the config file and send data them all.
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt()"
```
This version will explicitly try to obtain data for station `UK1234`, if its available on the Pi or PC. 
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt('UK1234')"
```

## CPU temperature and diskspace
`sendOtherData` can be used to publish CPU temperature and free diskspace on the disk holding `RMS_data`. 

The function currently doesn't support Windows, because CPU temp is not easy to obtain on Windows without 
administrator permissions (why? Ask Microsoft....). Hence for Windows this function will publish a value of zero for CPU temp. However if you have the CPU temp from some other source you can feed it into the function.

``` bash
# attempt to determine cpu temperature automatically - only works on Windows
python -c "from sendToMQTT import sendOtherData;sendOtherData()"
# supply a value for cputemp
python -c "from sendToMQTT import sendOtherData;sendOtherData(cputemp=$cputemp)"
```