#!/usr/bin/env python

################################################################################
# Generic helper functions
################################################################################

__all__ = ['TIMEDOUT', 'MINUTE', 'DEBUG_OFF', 'DEBUG_ON', 'DEBUG_ON_NO_FRAMEWORK',\
           'DumpConfigToLog', \
           'GetNextFreeUnit', 'FindUnitFromName', 'FindUnitFromDescription', 'AddTagToDescription', 'GetTagFromDescription', 'UpdateDevice', 'GetDevicesValue', 'GetDevicenValue', 'UpdateDeviceBatSig', 'TimeoutDevice', 'TimeoutDevicesByName', 'UpdateDeviceOptions', 'SecondsSinceLastUpdate', \
           'getConfigItemDB', 'setConfigItemDB', 'getConfigItemFile', 'setConfigItemFile', \
           'getCPUtemperature', \
           'FormatWebSocketMessage', 'FormatWebSocketPong', 'FormatWebSocketMessageDisconnect', \
           'getDistance' \
          ] 

#IMPORTS
import Domoticz
import datetime
import json
import os

#CONSTANTS
TIMEDOUT = 1               # timeout
MINUTE = 6                 # heartbeat is every 10s
DEBUG_OFF = 0              # set debug off
DEBUG_ON = 1               # set debug on
DEBUG_ON_NO_FRAMEWORK= 2   # set debug on but only message by Domoticz.Debug()

#DUMP THE PARAMETER
def DumpConfigToLog(Parameters, Devices):
    for parameter in Parameters:
        if Parameters[parameter] != '':
            Domoticz.Debug('Parameter {}: {}'.format(parameter, Parameters[parameter]))
    Domoticz.Debug('Got {} devices:'.format(len(Devices)))
    for device in Devices:
        Domoticz.Debug('Device {} {}'.format(device, Devices[device]))
        Domoticz.Debug('Device {} DeviceID:    {}'.format(device, Devices[device].DeviceID))
        Domoticz.Debug('Device {} Description: {}'.format(device, Devices[device].Description))
        Domoticz.Debug('Device {} LastLevel:   {}'.format(device, Devices[device].LastLevel))

#GET NEXT FREE DEVICE
def GetNextFreeUnit(Devices):
    # Find the next available unit, starting from 1
    unit = 1
    while unit in Devices:
        unit += 1
    Domoticz.Debug('Next free device unit {}'.format(unit))
    return unit
    
#GET DEVICE UNIT BY NAME
def FindUnitFromName(Devices, Parameters, Name, TruncSubName=False):
    if TruncSubName:
        for unit in [Unit for Unit in Devices if Devices[Unit].Name.startswith('{} - {}'.format(Parameters['Name'], Name))]:
            return unit
    else:
        for unit in [Unit for Unit in Devices if Devices[Unit].Name == '{} - {}'.format(Parameters['Name'], Name)]:
            return unit
    return False

#GET DEVICE UNIT BY USING THE DESCRIPTION FIELD
def FindUnitFromDescription(Devices, Parameters, Name):
    for unit in [Unit for Unit in Devices if GetTagFromDescription(Devices, Unit, 'Name') == '{} - {}'.format(Parameters['Name'], Name)]:
        return unit
    return False

#ADD TAG TO DESCRIPTION OF A DEVICE
def AddTagToDescription(Devices, Unit, tagName, tag):
    descriptions = [] if Devices[Unit].Description == '' else [ Devices[Unit].Description ]
    if 'Do not remove: ' in descriptions[0]:
        descriptions = descriptions[0].split('; ')
        for index, description in enumerate(descriptions):
            if description.startswith('Do not remove: '):
                Donotremove = json.loads(description[15:])
                Donotremove[0][tagName] = tag
                descriptions[index] = 'Do not remove: {}'.format(json.dumps(Donotremove))
    else: 
        descriptions += [ 'Do not remove: [{{"{}":"{}"}}]'.format(tagName, tag) ]
    Devices[Unit].Update(Description='; '.join(descriptions), nValue=Devices[Unit].nValue, sValue=Devices[Unit].sValue)

#GET TAG FROM DESCRIPTION OF A DEVICE
def GetTagFromDescription(Devices, Unit, tagName):
    tag = None
    descriptions = Devices[Unit].Description
    if 'Do not remove: ' in descriptions:
        descriptions = descriptions.split('; ')
        for description in descriptions:
            if description.startswith('Do not remove: '):
                Donotremove = json.loads(description[15:])
                if tagName in Donotremove[0]:
                    tag = Donotremove[0][tagName]
    return tag
     
#UPDATE THE DEVICE
def UpdateDevice(AlwaysUpdate, Devices, Unit, nValue, sValue, **kwargs):
    Updated = False
    if Unit in Devices:
        kwargs = { key : value for key, value in kwargs.items() if value != getattr(Devices[Unit], key, None) }
        default_kwargs = { 'TimedOut': 0 }
        kwargs = { **default_kwargs, **kwargs }
        if AlwaysUpdate or Devices[Unit].nValue != int(nValue) or Devices[Unit].sValue != str(sValue) or Devices[Unit].TimedOut != kwargs['TimedOut'] or len(kwargs)>1:
            Domoticz.Debug('Update {}: nValue {} - sValue {} - Other: {}'.format(Devices[Unit].Name, nValue, sValue, kwargs))
            Devices[Unit].Update(nValue=int(nValue), sValue=str(sValue), **kwargs)
            Updated = True
        else:
            if not kwargs.get('TimedOut', 0):
                Devices[Unit].Touch()
    return Updated

#GET sVALUE OF DEVICE
def GetDevicesValue(Devices, Unit):
    if Unit in Devices:
        return Devices[Unit].sValue
        
#GET nVALUE OF DEVICE
def GetDevicenValue(Devices, Unit):
    if Unit in Devices:
        return int(Devices[Unit].nValue)
        
#UPDATE THE BATTERY LEVEL AND SIGNAL STRENGTH OF A DEVICE
def UpdateDeviceBatSig(AlwaysUpdate, Devices, Unit, BatteryLevel=255, SignalLevel=12):
    if Unit in Devices:
        UpdateDevice(AlwaysUpdate, Devices, Unit, Devices[Unit].nValue, Devices[Unit].sValue, BatteryLevel=BatteryLevel, SignalLevel=SignalLevel) 

#SET DEVICE ON TIMED-OUT (OR ALL DEVICES)
def TimeoutDevice(Devices, All=True, Unit=0):
    if All:
        for x in Devices:
            UpdateDevice(False, Devices, x, Devices[x].nValue, Devices[x].sValue, TimedOut=TIMEDOUT)
    else:
        UpdateDevice(False, Devices, Unit, Devices[Unit].nValue, Devices[Unit].sValue, TimedOut=TIMEDOUT)

#SET DEVICES ON TIMED-OUT BY USING A TEXT IN THE DEVICE NAME
def TimeoutDevicesByName(Devices, Name):
    for x in Devices:
        if Name in Devices[x].Name:
            UpdateDevice(False, Devices, x, Devices[x].nValue, Devices[x].sValue, TimedOut=TIMEDOUT)

#UPDATE THE OPTIONS OF A DEVICE
def UpdateDeviceOptions(Devices, Unit, Options={}):
    if Unit in Devices:
        for key, value in Options.items():
            if key in Devices[Unit].Options and value != Devices[Unit].Options[key]:
                Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=Devices[Unit].sValue, Options=Options)
                Domoticz.Debug('Update options for {}: {}'.format(Devices[Unit].Name, Options))
                break

#GET THE SECONDS SINCE THE LASTUPDATE
def SecondsSinceLastUpdate(Devices, Unit):
    # try/catch due to http://bugs.python.org/issue27400
    try:
        timeDiff = datetime.now() - datetime.strptime(Devices[Unit].LastUpdate,'%Y-%m-%d %H:%M:%S')
    except TypeError:
        timeDiff = datetime.now() - datetime(*(time.strptime(Devices[Unit].LastUpdate,'%Y-%m-%d %H:%M:%S')[0:6]))
    return timeDiff

#GET CONFIGURATION VARIALBE (STORED IN DB)
def getConfigItemDB(Key=None, Default={}):
    Value = Default
    try:
        Config = Domoticz.Configuration()
        if (Key != None):
            Value = Config[Key] # only return requested key if there was one
        else:
            Value = Config      # return the whole configuration if no key
    except KeyError:
        Value = Default
    except Exception as inst:
        Domoticz.Error('Domoticz.Configuration read failed: {}'.format(inst))
    return Value

#SET CONFIGURATION VARIALBE (STORED IN DB)
def setConfigItemDB(Key=None, Value=None):
    Config = {}
    try:
        Config = Domoticz.Configuration()
        if (Key != None):
            Config[Key] = Value
        else:
            Config = Value  # set whole configuration if no key specified
        Config = Domoticz.Configuration(Config)
    except Exception as inst:
        Domoticz.Error('Domoticz.Configuration operation failed: {}'.format(inst))
    return Config
    
#CONFIGURATION HELPER: GET ITEM FROM FILE
def getConfigItemFile(Parameters, Key=None, Default={}):
    value = Default
    try:
        with open(Parameters['HomeFolder']+_PLUGIN_PARAMETERS_FILE) as infile:
            data = json.load(infile)
        if (Key != None):
            value = data[Key]    # only return requested key if there was one
        else:
            value = data         # return the whole configuration if no key
    except KeyError:
        value = Default
    except Exception as inst:
        Domoticz.Error('PluginParamter read file failed: {}.'.format(inst))
    return value
       
#CONFIGURATION HELPER: SET ITEM TO FILE
def setConfigItemFile(Parameters, Key=None, Value=None):
    data = {}
    try:
        if (Key != None):
            data[Key] = Value
        else:
            data = Value         # set whole configuration if no key specified
        with open(Parameters['HomeFolder']+_PLUGIN_PARAMETERS_FILE, 'w') as outfile:
            json.dump(data, outfile)
    except Exception as inst:
        Domoticz.Error('PluginParamter read file failed: {}.'.format(inst))
    return data

#CREATE WEBSOCKET TEXT MESSAGE (https://tools.ietf.org/html/rfc6455)
#CONDITIONS : ONLY TEXT FRAMES, ONE MESSAGE (FIN=1), NO MASKING, SMALLER THAN 127 BYTES PAYLOAD
def FormatWebSocketMessage(PayLoad):
    FormattedText = ''
    if len(PayLoad) < 127:
        FormattedText += '81'
        FormattedText += '{:02X}'.format(len(PayLoad))
    return bytes.fromhex(FormattedText) + bytes(PayLoad, 'utf-8')

#CREATE WEBSOCKET PONG MESSAGE (https://tools.ietf.org/html/rfc6455)
def FormatWebSocketPong(PayLoad):
    FormattedText = ''
    if len(PayLoad) < 127:
        FormattedText += '8A'
        FormattedText += '{:02X}'.format(len(PayLoad))
    return bytes.fromhex(FormattedText) + bytes(PayLoad, 'utf-8')

#CREATE WEBSOCKET DISCONNECT MESSAGE (https://tools.ietf.org/html/rfc6455)
def FormatWebSocketMessageDisconnect():
    FormattedText = '8800'
    return bytes.fromhex(FormattedText)

#GET CPU TEMPERATURE
def getCPUtemperature():
    try:
        res = os.popen('cat /sys/class/thermal/thermal_zone0/temp').readline()
    except:
        res = '0'
    return round(float(res)/1000,1)
    
#CALCULATE DISTANCE BASED ON GPS COORDINATES
from math import radians, sin, cos, atan2, sqrt
def getDistance(origin, destination, unit='km'):
    radius = 6371 # km

    dlat = radians(destination[0]-origin[0])
    dlon = radians(destination[1]-origin[1])
    a = sin(dlat/2) * sin(dlat/2) + cos(radians(origin[0])) \
        * cos(radians(destination[0])) * sin(dlon/2) * sin(dlon/2)
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    d = radius * c

    return d*1000 if unit=='m' else d 


