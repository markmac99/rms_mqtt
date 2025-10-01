#
# Python script to publish meteor data to MQTT
# Copyright (C) Mark McIntyre
#
#
# first run "pip install paho-mqtt"
# then run "python sendToMQTT.py"
# it will create topics:
#   meteorcams/youcamid/detectedcount
#   meteorcams/youcamid/meteorcount
#   meteorcams/youcamid/datestamp
# Which are respectively, the total reported in the log file, the total in the FTPdetect file, 
# and the time the script ran at

import paho.mqtt.client as mqtt
import datetime
import os
import sys
import glob
import logging
import requests
import configparser

import RMS.ConfigReader as cr

log = logging.getLogger()


def getRMSConfig(statid, localcfg):
    rmscfg = os.path.expanduser(f'~/source/Stations/{statid}/.config')
    if not os.path.isfile(rmscfg):
        rmscfg = os.path.join(localcfg['rms']['rmsdir'], '.config')
    cfg = cr.parse(os.path.expanduser(rmscfg))
    return cfg


# The callback function. It will be triggered when trying to connect to the MQTT broker
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected success")
    else:
        print("Connected fail with code", rc)


def on_publish(client, userdata, result):
    #print('data published - {}'.format(result))
    return


def getMqClient(localcfg=None, clientname='random'):
    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    client = mqtt.Client(clientname)
    client.on_connect = on_connect
    client.on_publish = on_publish
    if localcfg['mqtt']['cafile'] != '':
        client.tls_set(localcfg['mqtt']['cafile'])
    if localcfg['mqtt']['username'] != '':
        client.username_pw_set(localcfg['mqtt']['username'], localcfg['mqtt']['password'])
    client.connect(broker, mqport, 60)
    return client


def getLoggedInfo(cfg):
    datestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
    logfs = glob.glob(os.path.join(log_dir, 'log*.log*'))
    logfs.sort(key=lambda x: os.path.getmtime(x))
    if len(logfs) == 0:
        return 0,0,0,datestamp
    dd=[]
    i=1
    
    while len(dd) == 0 and i < len(logfs) + 1:
        last_log = logfs[-i]
        lis = open(last_log,'r').readlines()
        dd = [li for li in lis if 'Data directory' in li]
        if len(dd) > 0:
            break
        i = i + 1
    # print('last log', last_log)
    totli = [li for li in lis if 'TOTAL' in li]
    detectedcount = 0
    if len(totli) > 0:
        detectedcount = int(totli[0].split(' ')[4].strip())

    current_log = logfs[-1]
    lis = open(current_log,'r').readlines()
    sc = [li for li in lis if 'Detected stars' in li]
    starcount = 0
    if len(sc) > 0:
        try:
            starcount = int(sc[-1].split()[5])
        except Exception:
            pass

    meteorcount = 0
    capdir = os.path.join(cfg.data_dir, 'CapturedFiles')
    yest = datetime.datetime.now() + datetime.timedelta(days=-1)
    datedir = glob.glob(f'*{yest.strftime("%Y%m%d")}*')
    caps = glob.glob(os.path.join(capdir, f'{datedir}*'))
    caps.sort(key=lambda x: os.path.getmtime(x))
    if len(caps)> 0:
        capdir = caps[-1]
    else:
        return detectedcount, meteorcount, 0, datestamp

    ftpfs = glob.glob(os.path.join(capdir, 'FTPdetectinfo*.txt'))
    ftpf = [f for f in ftpfs if 'backup' not in f and 'unfiltered' not in f]
    meteorcount = 0
    if len(ftpf) > 0:
        lis = open(ftpf[0],'r').readlines()
        mc = [li for li in lis if 'Meteor Count' in li]
        meteorcount = int(mc[0].split('=')[1].strip())
    # if meteorcount is nonzero but detected count is zero then the logfile was malformed
    if detectedcount == 0 and meteorcount > 0:
        detectedcount = meteorcount

    return detectedcount, meteorcount, starcount, datestamp


def sendMatchdataToMqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))

    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]
    ret = 0
    client = getMqClient(localcfg)
    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)

        topicbase = 'meteorcams' 
        if 'test' not in statid:
            statid = cfg.stationID.lower()
        apiurl = 'https://api.ukmeteors.co.uk/matches'
        dtstr = datetime.datetime.now().strftime('%Y%m%d')
        apicall = f'{apiurl}?reqtyp=station&reqval={dtstr}&statid={cfg.stationID}'
        res = requests.get(apicall)
        if res.status_code == 200:
            rawdata=res.text.strip()
            matchcount = rawdata.count('orbname')
        else:
            matchcount = 0
        dtstr = (datetime.datetime.now() + datetime.timedelta(days=-1)).strftime('%Y%m%d')
        apicall = f'{apiurl}?reqtyp=station&reqval={dtstr}&statid={cfg.stationID}'
        res = requests.get(apicall)
        if res.status_code == 200:
            rawdata=res.text.strip()
            v1 = rawdata.count(f'{dtstr}_1')
            v2 = rawdata.count(f'{dtstr}_2')
            matchcount = matchcount + v1 + v2
        if localcfg['mqtt']['username'] != '':
            client.username_pw_set(localcfg['mqtt']['username'], localcfg['mqtt']['password'])
        topic = f'{topicbase}/{statid}/matchcount'
        ret = client.publish(topic, payload=matchcount, qos=0, retain=False)
        log.info(f'there were {matchcount} matches last night for {statid}')
    return ret


def sendLiveMeteorCount(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]

    client = getMqClient(localcfg)
    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)

        topicbase = 'meteorcams' 
        if 'test' not in statid:
            statid = cfg.stationID.lower()

        log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
        logfs = glob.glob(os.path.join(log_dir, 'ukmonlive*.log*'))
        logfs.sort(key=lambda x: os.path.getmtime(x))
        if len(logfs) == 0:
            msg = 0
        else:
            lis = open(logfs[-1]).readlines()
            msg = len([x for x in lis if 'uploading FF' in x])

        subtopic = 'livecmeteorount'
        topic = f'{topicbase}/{statid}/{subtopic}'
        _ = client.publish(topic, payload=msg, qos=0, retain=False)
    client.disconnect()
    return 


def sendToMqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]

    client = getMqClient(localcfg)
    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)
        topicbase = 'meteorcams' 
        if 'test' not in statid:
            statid = cfg.stationID.lower()
        print(f'processing {statid}')
        detectioncount, metcount, _, datestamp = getLoggedInfo(cfg)
        if 'test' in statid:
            metcount = -1
            detectioncount = -2
        msgs =[detectioncount, metcount, datestamp]

        subtopics = ['detectioncount','meteorcount','timestamp']
        broker = localcfg['mqtt']['broker']
        for subtopic, msg in zip(subtopics, msgs): 
            topic = f'{topicbase}/{statid}/{subtopic}'
            ret = client.publish(topic, payload=msg, qos=2, retain=True)
            print(f'send {msg} to {topic} on {broker}, result {ret}')

    client.disconnect()
    return ret


def sendStarCountToMqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]
    ret = 0
    client = getMqClient(localcfg)
    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)
        topicbase = 'meteorcams' 
        if 'test' not in statid:
            statid = cfg.stationID.lower()

        log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
        logfs = glob.glob(os.path.join(log_dir, 'log*.log*'))
        logfs.sort(key=lambda x: os.path.getmtime(x))
        starcount = 0
        tstamp = None
        if len(logfs) > 0:
            current_log = logfs[-1]
            print(f'current log is {current_log}')
            lis = open(current_log,'r').readlines()
            sc = [li for li in lis if 'Detected stars' in li]
            if len(sc) > 0:
                try:
                    starcount = int(sc[-1].split()[5])
                    tstamp = sc[-1].split('-')[0]
                except Exception:
                    pass
            else:
                current_log = logfs[-2]
                print(f'current log is {current_log}')
                lis = open(current_log,'r').readlines()
                sc = [li for li in lis if 'Detected stars' in li]
                if len(sc) > 0:
                    try:
                        starcount = int(sc[-1].split()[5])
                        tstamp = sc[-1].split('-')[0]
                    except Exception:
                        pass

            if tstamp is not None: 
                topic = f'{topicbase}/{statid}/starcount'
                print(f'{tstamp}: starcount for {statid} is {starcount}')
                ret = client.publish(topic, payload=starcount, qos=0, retain=False)
    client.disconnect()
    return ret


def sendOtherData(cputemp, diskspace, statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    
    cfg = getRMSConfig(statid, localcfg)
    if statid == '':
        statid = os.uname()[1]
    if 'test' not in statid:
        statid = cfg.stationID.lower()

    client = getMqClient(localcfg)
    if len(cputemp) > 2:
        cputemp = cputemp[:-2]
    else:
        cputemp = 0
    if len(diskspace) > 1:
        diskspace = diskspace[:-1]
    else:
        diskspace = 0
    topic = f'meteorcams/{statid}/cputemp'
    ret = client.publish(topic, payload=cputemp, qos=0, retain=True)
    topic = f'meteorcams/{statid}/diskspace'
    ret = client.publish(topic, payload=diskspace, qos=0, retain=True)
    client.disconnect()
    return ret


def test_mqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    cfg = getRMSConfig(statid, localcfg)
    client = getMqClient(localcfg)
    if statid == '':
        statid = os.uname()[1]
    if 'test' not in statid:
        statid = cfg.stationID.lower()

    topic = f'testing/{statid}/test'
    ret = client.publish(topic, payload=f'test from {statid}', qos=0, retain=False)
    print("send to {}, result {}".format(topic, ret))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python sendToMqtt stationid')
        exit(0)
    if len(sys.argv) > 2:
        test_mqtt(sys.argv[1])
    else:
        sendToMqtt(sys.argv[1])
