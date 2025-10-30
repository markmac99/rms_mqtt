# Monitoring and RMS camera with MQ 

If you are running OpenHAB, Home Assistant or a similar home automation software you can monitor the RMS meteor camera with [MQTT](https://mqtt.org/).  

## What is MQTT? 
MQTT is a lightweight messaging protocol widely used in the IoT (Internet of Things) world to communicate between smart devices. For example using MQTT your home automation software can monitor and control smart plugs, switches, weatherstations, doorbells and so forth.

For our purposes, we are going to monitor detection, meteor and star counts, camera status, and its useful to track CPU temperature, memory and disk space usage. 
If you're contributing to UKMON you can also obtain a count of matched events involving your camera. 

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
Copy `config.ini.example` to `config.ini` and update it with the details of your MQ broker. If your uses SSL, you'll probably want port 8883 but otherwise its normally 1883.

If you're *not* using a multi-cam setup, update `RMSDIR` with the full path of the folder containing RMS, for example `/home/rms/source/RMS`. For multi-cam setups, the code will automatically find the correct configuration files. This might also be required on some non-multicam setups if your RMS source is in an unusual place. 

Add your Camera IDs to the `[stations]` section, as shown below. You can add/remove IDs as needed. 
``` bash
[stations]
ID1=XX0001
ID2=XX0002
```

### Testing
You can test functionality by running the following in a Terminal window:
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt('testing')"
```
This will publish to a topic `meteorcams/testing`. 

## Usage

There are five functions that can be used to submit meteor-related data to MQ:

* `sendToMqtt` will publish the latest count of detections, meteors, and the next capture start-time. 
* `sendStarCountToMqtt` will publish the latest star count. 
* `sendCameraStatus` will check the camera module can be pinged and return True or False accordingly. 
* `sendOtherData` will publish some system performance metrics - see below. 

And if and only if you're a UKMON contributor you can use the following: 
* `sendLiveMeteorCount` will publish a live count of potential detections.  
* `sendMatchdataToMqtt` this will publish the count of confirmed matches your station was involved in. 

### Tracking Star and Live Detection Counts and Pi Statistics
To track the star count and live meteor counts, camera status, and system metrics at ten minute intervals, add an entry to the crontab like the one below. 

```bash
*/10 * * * * /home/rms/source/tackley-tools/logLiveStats.sh >> /dev/null 2>&1
```

### Tracking Meteor Counts
This should be done in the morning immediately after data has been uploaded, so its best to invoke `sendToMqtt()` from the RMS post-processing hook. A minimal post-processing hook script is available in this repository but its left as an exercise for the reader to work out how to integrate this with RMS and any other post-processing scripts. 

The bash script `logMeteorStats.sh` included in this repo shows another way to use `sendToMqtt()`. However, as noted above you should only invoke this after RMS has uploaded to GMN so as to capture the current data. Its not useful to call this from cron because it will post the same data over and over.

### Example use from the commandline
All functions can be invoked from the Terminal / commandline as shown in the examples below. 

This invocation will read the station list from the config file and send data for them all.
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt()"
```
This version will explicitly try to obtain data for station `UK1234`, if its available on the Pi or PC. 
``` bash
python -c "from sendToMQTT import sendToMqtt;sendToMqtt(statid='UK1234')"
```

### CPU temperature, diskspace and memory usage
`sendOtherData` can be used to publish CPU temperature, memory and swap usage and free diskspace on the disk holding `RMS_data`. 

CPU  temp is not easy to obtain on Windows without 
administrator permissions (Ask Microsoft....). Hence for Windows this function will publish a CPU temperature of zero. 

Note that the hardware data data are published to a topic `meteorcams/{camid}/` where camid is the the first station listed in the config file. 

``` bash
# attempt to determine cpu temperature automatically - only works on Windows
python -c "from sendToMQTT import sendOtherData;sendOtherData()"
# supply a value for cputemp
python -c "from sendToMQTT import sendOtherData;sendOtherData(cputemp=$cputemp)"
```

As with the other functions you can also supply `statid='stationid'` to publish data to a topic `meteorcams/stationid`. This is useful for testing. 

## Thanks
Many thanks to Peter McKellar in Aotearoa / NZ for testing and for suggesting improvements and enhancements. Peter's cameras, located on the opposite side of the world to me, were essential in debugging timezone and geographical assumptions and errors in my original code. Peter also proposed a number of useful additions to the module which i had not considered. 