#
# Python script to publish meteor data to MQTT
# Copyright (C) Mark McIntyre
#
# read the README for information about how to install and use

from paho.mqtt.publish import multiple
import datetime
import os
import sys
import glob
import requests
import configparser
import shutil
import ssl
import platform

import RMS.ConfigReader as cr


def getfreemem():
    if sys.platform != 'win32':
        lis = open('/proc/meminfo', 'r').readlines()
        total = [x for x in lis if 'MemTotal' in x][0].strip().split(':')
        avail = [x for x in lis if 'MemAvailable' in x][0].strip().split(':')
        total = float(total[1].replace('kB',''))
        avail = float(avail[1].replace('kB',''))
        memused = total - avail
        memusedpct = round(memused * 100 / total, 2)
        swtotal = [x for x in lis if 'SwapTotal' in x][0].strip().split(':')
        swavail = [x for x in lis if 'SwapFree' in x][0].strip().split(':')
        swtotal = float(swtotal[1].replace('kB',''))
        swavail = float(swavail[1].replace('kB',''))
        swapused = swtotal - swavail
        swapusedpct = round(swapused * 100 / total, 2)
    else:
        memused = 0
        memusedpct = 0
        swapused = 0
        swapusedpct = 0
        print('mem usage not supported on Windows')
    return memused, memusedpct, swapused, swapusedpct


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
    print(f'data published - {result}')
    return


def getLoggedInfo(cfg, camname):
    datestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
    logfs = glob.glob(os.path.join(log_dir, f'log_{camname.upper()}*.log*'))
    logfs.sort(key=lambda x: os.path.getmtime(x))
    logfs = sorted(logfs, reverse=True)
    if len(logfs) == 0:
        return 0,0,0,datestamp, ''

    starcount = 0
    meteorcount = 0
    detectedcount = None
    nextcapstart = None

    for logf in logfs:
        print(f'checking in {logf}')
        lis = open(logf,'r').readlines()
        # get nextcapstart
        if not nextcapstart:
            lst = [li for li in lis if 'Next start time:' in li]
            if len(lst) != 0:
                lst = lst[-1]
                nextcapstart = lst.split(': ')[1].strip()
                print(f' nextcapstart {nextcapstart}')
        # get total detections reported in the log
        if not detectedcount:
            totli = [li for li in lis if 'TOTAL' in li]
            if len(totli) > 0:
                detectedcount = int(totli[0].split(' ')[4].strip())
        if detectedcount is not None and nextcapstart is not None:
            break

    # get current star count reported in the log
    lis = open(logfs[0],'r').readlines()
    sc = [li for li in lis if 'Detected stars' in li]
    if len(sc) > 0:
        try:
            starcount = int(sc[-1].split()[5])
        except Exception:
            starcount = 0

    # count the number of meteors reported in the ftpdetect file
    capdir = os.path.join(cfg.data_dir, 'CapturedFiles')
    yest = datetime.datetime.now() + datetime.timedelta(days=-1)
    datedir = glob.glob(f'*{yest.strftime("%Y%m%d")}*')
    caps = glob.glob(os.path.join(capdir, f'{datedir}*'))
    caps.sort(key=lambda x: os.path.getmtime(x))
    if len(caps) > 0:
        capdir = sorted(caps, reverse=True)[0]
        ftpfs = glob.glob(os.path.join(capdir, 'FTPdetectinfo*.txt'))
        ftpf = [f for f in ftpfs if 'backup' not in f and 'unfiltered' not in f]
        if len(ftpf) > 0:
            lis = open(ftpf[0],'r').readlines()
            mc = [li for li in lis if 'Meteor Count' in li]
            meteorcount = int(mc[0].split('=')[1].strip())

    # some sanity checks 
    if not detectedcount:
        detectedcount = 0
    if not nextcapstart:
        nextcapstart = ''
    detectedcount = max(detectedcount, meteorcount)

    return detectedcount, meteorcount, starcount, datestamp, nextcapstart


def sendMatchdataToMqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))

    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]
    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    auth = {'username': localcfg['mqtt']['username'], 'password': localcfg['mqtt']['password']}
    if mqport == 8883:
        tls = {'ca_certs':None, 'cert_reqs':ssl.CERT_REQUIRED, 'tls_version':ssl.PROTOCOL_TLS}
    else:
        tls = None
    clientid = 'sendmatches'
    msgs = []

    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)
        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()

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
        topic = f'meteorcams/{camname}/matchcount'
        print(f'{topic} {matchcount}')
        msgs.append((topic, matchcount, 1))
    # now send everything
    if len(msgs) > 0:
        ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    else:
        print('nothing to publish')
        ret = 1
    return ret


def sendLiveMeteorCount(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]

    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    auth = {'username': localcfg['mqtt']['username'], 'password': localcfg['mqtt']['password']}
    if mqport == 8883:
        tls = {'ca_certs':None, 'cert_reqs':ssl.CERT_REQUIRED, 'tls_version':ssl.PROTOCOL_TLS}
    else:
        tls = None
    clientid = 'sendlivemeteors'
    msgs = []

    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)
        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()

        log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
        logfs = glob.glob(os.path.join(log_dir, 'ukmonlive*.log*'))
        logfs.sort(key=lambda x: os.path.getmtime(x))
        if len(logfs) == 0:
            msg = 0
        else:
            lis = open(logfs[-1]).readlines()
            msg = len([x for x in lis if 'uploading FF' in x])

        topic = f'meteorcams/{camname}/livecmeteorount'
        print(f'{topic} {msg}')
        msgs.append((topic, msg, 1))
    # now send everything
    if len(msgs) > 0:
        ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    else:
        print('nothing to publish')
        ret = 1
    return ret


def sendToMqtt(statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
    else:
        statids = [statid]

    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    auth = {'username': localcfg['mqtt']['username'], 'password': localcfg['mqtt']['password']}
    if mqport == 8883:
        tls = {'ca_certs':None, 'cert_reqs':ssl.CERT_REQUIRED, 'tls_version':ssl.PROTOCOL_TLS}
    else:
        tls = None

    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)
        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()

        detectioncount, metcount, starcount, datestamp, nextcapstart = getLoggedInfo(cfg, camname)
        print(f'logged info detcount {detectioncount} metcount {metcount} starcount {starcount} nextstart {nextcapstart}')
        msgs = [(f'meteorcams/{camname}/detectioncount', detectioncount, 1),
                (f'meteorcams/{camname}/meteorcount', metcount,1),
                (f'meteorcams/{camname}/timestamp',datestamp,1),
                (f'meteorcams/{camname}/nextcapstart', nextcapstart,1)]
        ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=camname, keepalive=60, auth=auth, tls=tls)
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

    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    auth = {'username': localcfg['mqtt']['username'], 'password': localcfg['mqtt']['password']}
    if mqport == 8883:
        tls = {'ca_certs':None, 'cert_reqs':ssl.CERT_REQUIRED, 'tls_version':ssl.PROTOCOL_TLS}
    else:
        tls = None
    clientid = 'starcount'
    msgs = []
    for statid in statids:
        cfg = getRMSConfig(statid, localcfg)

        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()

        log_dir = os.path.join(cfg.data_dir, cfg.log_dir)
        logfs = glob.glob(os.path.join(log_dir, f'log_{camname}*.log*'))
        logfs.sort(key=lambda x: os.path.getmtime(x))
        logfs = sorted(logfs, reverse=True)
        starcount = 0
        for current_log in logfs:
            print(f'current log is {current_log}')
            lis = open(current_log,'r').readlines()
            sc = [li for li in lis if 'Detected stars' in li]
            if len(sc) > 0:
                try:
                    starcount = int(sc[-1].split()[5])
                    break
                except Exception:
                    starcount = 0
        topic = f'meteorcams/{camname}/starcount'
        print(f'{topic} {starcount}')
        msgs.append((topic, starcount, 1))

    # now send everything
    if len(msgs) > 0:
        ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    else:
        print('nothing to publish')
        ret = 1
    return ret


def sendOtherData(cputemp=None, statid=''):
    srcdir = os.path.split(os.path.abspath(__file__))[0]
    localcfg = configparser.ConfigParser()
    localcfg.read(os.path.join(srcdir, 'config.ini'))
    
    broker = localcfg['mqtt']['broker']
    mqport = int(localcfg['mqtt']['mqport'])
    auth = {'username': localcfg['mqtt']['username'], 'password': localcfg['mqtt']['password']}
    if mqport == 8883:
        tls = {'ca_certs':None, 'cert_reqs':ssl.CERT_REQUIRED, 'tls_version':ssl.PROTOCOL_TLS}
    else:
        tls = None
    clientid = 'otherdata'
    msgs = []

    # use the 1st station id if nothing provided on the commandline
    if statid == '':
        statids = [x[1].upper() for x in localcfg.items('stations')]
        statid = statids[0]
    cfg = getRMSConfig(statid, localcfg)
    
    usage = shutil.disk_usage(cfg.data_dir)
    diskspace = round((usage.used/usage.total)*100, 2)

    if 'test' in statid:
        camname = statid
    else:
        camname = platform.node()
        if 'test' not in camname:
            camname = cfg.stationID.lower()

    if cputemp is None:
        if sys.platform != 'win32':
            cputemp = float(open('/sys/class/thermal/thermal_zone0/temp', 'r').readline().strip())/1000
        else:
            print('cputemp not supported on windows')
            cputemp=0

    memused, memusedpct, swapused, swapusedpct = getfreemem()

    msgs = [(f'meteorcams/{camname}/cputemp', cputemp, 1),
            (f'meteorcams/{camname}/diskspace', diskspace,1),
            (f'meteorcams/{camname}/memused', memused,1),
            (f'meteorcams/{camname}/memusedpct', memusedpct,1),
            (f'meteorcams/{camname}/swapusedpct', swapused,1),
            (f'meteorcams/{camname}/swapusedpct', swapusedpct,1)]
    ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    return ret


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python sendToMqtt stationid')
        exit(0)
    sendToMqtt(sys.argv[1])
