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
import re
import subprocess

try:
    import RMS.ConfigReader as cr
    from RMS.CaptureDuration import captureDuration
    gotRMS = True
except Exception:
    gotRMS = False


def ping(host, count=1):
    # ping the target. Note that on Windows, ping returns True even if the host was
    # unreachable
    param = '-n' if platform.system().lower()=='windows' else '-c'
    command = ['ping', param, str(count), host]
    #print(f'pinging {command}')
    try:
        pingres = subprocess.check_output(command)
        if b'timed out' in pingres or b'unreachable' in pingres or b'Lost = 1' in pingres: 
            print('ping timeout or unreachable')
            return 0
        return 1
    except Exception as e:
        print(f'ping failed {e}')
        return 0


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
    if gotRMS:
        rmscfg = os.path.expanduser(f'~/source/Stations/{statid}/.config')
        if not os.path.isfile(rmscfg):
            rmscfg = os.path.join(localcfg['rms']['rmsdir'], '.config')
        cfg = cr.parse(os.path.expanduser(rmscfg))
        topicroot = 'meteorcams'
    else:
        class dummycfg():
            def __init__(self):
                self.data_dir = '/'
                self.stationID = platform.node()
        cfg = dummycfg()
        topicroot = 'servers'
    return cfg, topicroot


def getLoggedInfo(cfg, camname, starcountonly=False):
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

    if not starcountonly:
        # see if we can get next cap start from RMS's builtin routine
        if gotRMS:
            nsc = True
            doff = 0
            while nsc is True and doff < 24:
                dtadj = datetime.datetime.now()+datetime.timedelta(hours=doff)
                nsc, _ = captureDuration(cfg.latitude, cfg.longitude, cfg.elevation, dtadj)
                print(nsc)
                doff = doff + 1
                nextcapstart = str(nsc) + ' UTC'
                print('got next cap start from RMS')

        for logf in logfs:
            print(f'checking for detections in {logf}')
            lis = open(logf,'r').readlines()
            # get nextcapstart if not already obtained
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

        # count the number of meteors reported in the ftpdetect file
        arcdir = os.path.join(cfg.data_dir, 'ArchivedFiles')
        arcs = glob.glob(os.path.join(arcdir,'*'))
        arcs = [arc for arc in arcs if os.path.isdir(arc)]
        if len(arcs) > 0: 
            arcs = sorted(arcs, reverse=True)
            ftpfs = glob.glob(os.path.join(arcs[0], 'FTPdetectinfo*.txt'))
            ftpf = [f for f in ftpfs if 'backup' not in f and 'unfiltered' not in f]
            if len(ftpf) > 0:
                lis = open(ftpf[0],'r').readlines()
                mc = [li for li in lis if 'Meteor Count' in li]
                meteorcount = int(mc[0].split('=')[1].strip())

    # get current star count reported in the log
    lis = open(logfs[0],'r').readlines()
    sc = [li for li in lis if 'Detected stars' in li]
    if len(sc) > 0:
        try:
            starcount = int(sc[-1].split()[5])
        except Exception:
            starcount = 0

    # some sanity checks 
    if not detectedcount:
        detectedcount = 0
    if not nextcapstart:
        nextcapstart = ''
    detectedcount = max(detectedcount, meteorcount)

    return detectedcount, meteorcount, starcount, datestamp, nextcapstart


def sendCameraStatus(statid=''):
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
        cfg, _ = getRMSConfig(statid, localcfg)
        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()
        camipaddr = re.findall(r"[0-9]+(?:\.[0-9]+){3}", cfg.deviceID)[0]
        camerastatus = ping(camipaddr)
        topic = f'meteorcams/{camname}/camerastatus'
        print(f'{topic} {camerastatus}')
        msgs.append((topic, camerastatus, 1))
    # now send everything
    if len(msgs) > 0:
        ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    else:
        print('nothing to publish')
        ret = 1
    return ret


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
        cfg, _ = getRMSConfig(statid, localcfg)
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
        cfg, _ = getRMSConfig(statid, localcfg)
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
        cfg, _ = getRMSConfig(statid, localcfg)
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
                (f'meteorcams/{camname}/starcount', starcount,1),
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
        cfg, _ = getRMSConfig(statid, localcfg)

        if 'test' in statid:
            camname = statid
        else:
            camname = platform.node()
            if 'test' not in camname:
                camname = cfg.stationID.lower()

        _, _, starcount, _, _ = getLoggedInfo(cfg, camname, starcountonly=True)
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
    cfg, topicroot = getRMSConfig(statid, localcfg)
    
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

    msgs = [(f'{topicroot}/{camname}/cputemp', cputemp, 1),
            (f'{topicroot}/{camname}/diskspace', diskspace,1),
            (f'{topicroot}/{camname}/memused', memused,1),
            (f'{topicroot}/{camname}/memusedpct', memusedpct,1),
            (f'{topicroot}/{camname}/swapused', swapused,1),
            (f'{topicroot}/{camname}/swapusedpct', swapusedpct,1)]
    ret = multiple(msgs=msgs, hostname=broker, port=mqport, client_id=clientid, keepalive=60, auth=auth, tls=tls)
    return ret


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python sendToMqtt stationid')
        exit(0)
    sendToMqtt(sys.argv[1])
