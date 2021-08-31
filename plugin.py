#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Fan Python Plugin
#
# Author: Filip Demaertelaere
#
# Plugin to get the download volume for Telenet
# Implemenation based on https://github.com/KillianMeersman/telemeter
#
"""
<plugin key="Telenet" name="Telenet" author="Filip Demaertelaere" version="1.0.0">
    <params>
        <param field="Mode1" label="Username" width="200px" required="true" default=""/>
        <param field="Mode2" label="Password" width="200px" required="true" default="" password="true"/>
        <param field="Mode5" label="Hours between update" width="120px" required="true" default="1"/>
        <param field="Mode6" label="Debug" width="120px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="True"/>
            </options>
        </param>
    </params>
</plugin>
"""

#IMPORTS
import sys
major,minor,x,y,z = sys.version_info
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.append('/usr/local/lib/python'+str(major)+'.'+str(minor)+'/dist-packages')
from urllib.parse import urlparse
import Domoticz
import json

#DEVICES TO CREATE
_UNIT_USAGE = 1

#DEFAULT IMAGE
_IMAGE = "Telenet"

#THE HAERTBEAT IS EVERY 10s
_MINUTE = 6
_HOUR = _MINUTE*60

#VALUE TO INDICATE THAT THE DEVICE TIMED-OUT
_TIMEDOUT = 1

#DEBUG
_DEBUG_OFF = 0
_DEBUG_ON = 1

#TELENET INFORMATION
TELENET_API = 'api.prd.telenet.be'
TELENET_LOGIN = 'login.prd.telenet.be'
TELENET_WWW2 = 'www2.telenet.be'
TELENET_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.0%z"

################################################################################
# Start Plugin
################################################################################

class BasePlugin:

    def __init__(self):
        self.debug = _DEBUG_OFF
        self.runAgain = _HOUR
        self.state = None
        self.nonce = None
        self.cookie = None
        self.dtcookie = None
        self.X_TOKEN_XSRF = None
        self.url_redirect = None
        self.login_page = False
        self.login_successful = False
        self.telemeter_data = None
        return

    def onStart(self):
        Domoticz.Debug("onStart called")

        # Debugging On/Off
        if Parameters["Mode6"] == "Debug":
            self.debug = _DEBUG_ON
        else:
            self.debug = _DEBUG_OFF
        Domoticz.Debugging(self.debug)
        
        self.runAgain = _HOUR * float(Parameters["Mode5"].replace(',','.'))

        # Check if images are in database
        if _IMAGE not in Images:
            Domoticz.Image("Telenet.zip").Create()

        # Create devices (USED BY DEFAULT)
        CreateDevicesUsed()

        # Create devices (NOT USED BY DEFAULT)
        CreateDevicesNotUsed()

        # Set all devices as timed out
        TimeoutDevice(All=True)

        # Connection parameters to start...
        self.httpConnAPI = Domoticz.Connection(Name="TelenetAPI", Transport="TCP/IP", Protocol="HTTPS", Address=TELENET_API, Port='443')
        self.httpConnAPI.Connect()

        # Global settings
        DumpConfigToLog()

    def onStop(self):
        Domoticz.Debug("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called (" + Connection.Name + ") with status=" + str(Status))
        if Status == 0:
            if Connection.Name == 'TelenetAPI':
                if self.login_successful:
                    self.Get_Telemeter()
                else:
                    self.Get_oauth2_token()
            if Connection.Name == 'TelenetLogin':
                self.Login()
            if Connection.Name == 'TelenetWWW2':
                self.Redirect()
        else:
            Domoticz.Debug("Error received on establishing connections!")
            TimeoutDevice(False, _UNIT_USAGE)

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called: {} - {}".format(Connection.Name, Data['Status']))
        #Domoticz.Debug(json.dumps(Data['Headers']))
        
        # Login page not yet done... "HTTP Unauthorised" received
        if not self.login_page and Connection.Name == 'TelenetAPI' and int(Data['Status']) == 401:
            self.state, self.nonce = Data['Data'].decode("utf-8").split(",", maxsplit=2)
            for cookie in Data['Headers']['Set-Cookie']:
                if cookie.startswith('dtCookie'):
                    self.cookie = cookie.split(";")[0]
            # Start-up connection for login
            self.httpConnLogin = Domoticz.Connection(Name="TelenetLogin", Transport="TCP/IP", Protocol="HTTPS", Address=TELENET_LOGIN, Port='443')
            self.httpConnLogin.Connect()

        # Login page not yet done... Redirect received for the login
        if not self.login_page and Connection.Name == 'TelenetLogin' and int(Data['Status']) == 302:
            self.cookie = ''
            for cookie in Data['Headers']['Set-Cookie']:
                if cookie.startswith('dtCookie'):
                    self.dtcookie = cookie.split(";")[0]
                    self.cookie += '; {}'.format(self.dtcookie)
                if cookie.startswith('lang') or cookie.startswith('OAUTHSESSIONID'):
                    self.cookie += '; {}'.format(cookie.split(";")[0])
            self.cookie = self.cookie[2:]
            self.url_redirect = Data['Headers']['Location']
            # Execute redirection
            self.Redirect()
            
        # Login page not yet done... Login page loaded to start login
        if not self.login_page and Connection.Name == 'TelenetLogin' and int(Data['Status']) == 200:
            self.login_page = True
            # Start login
            self.Login_Do()

        # Login page received and login done... Request received to redirect
        if self.login_page and Connection.Name == 'TelenetLogin' and int(Data['Status']) == 302:
            if not 'callback?code' in Data['Headers']['Location']:
                self.cookie = self.dtcookie
                for cookie in Data['Headers']['Set-Cookie']:
                    if cookie.startswith('lang') or cookie.startswith('OAUTHSESSIONID') or cookie.startswith('OIDC_SSO_ID') or cookie.startswith('CURRENT_OIDC_SSO') or cookie.startswith('OIDC_FRONTCHANNEL_LOGOUT_CLIENTS') or cookie.startswith('CURRENT_OIDC_FRONTCHANNEL_LOGOUT_CLIENTS'):
                        self.cookie += '; {}'.format(cookie.split(";")[0])
            self.url_redirect = Data['Headers']['Location']
            # Execute redirection
            self.Redirect()
            
        # Login page received and login done... Request received to temporary redirect
        if self.login_page and Connection.Name == 'TelenetAPI' and int(Data['Status']) == 307:
            self.cookie = self.dtcookie
            for cookie in Data['Headers']['Set-Cookie']:
                if cookie.startswith('lang') or cookie.startswith('OCASESSIONID'):
                    self.cookie += '; {}'.format(cookie.split(";")[0])
                if cookie.startswith('TOKEN-XSRF'):
                    self.X_TOKEN_XSRF = cookie.split(";")[0][11:]
                    self.cookie += '; {}'.format(cookie.split(";")[0])
            self.url_redirect = Data['Headers']['Location']
            # To redirect, connection to other server is required
            self.httpConnWWW2 = Domoticz.Connection(Name="TelenetWWW2", Transport="TCP/IP", Protocol="HTTPS", Address=TELENET_WWW2, Port='443')
            self.httpConnWWW2.Connect()
            
        # Login done, get OAUTH2 token    
        if Connection.Name == 'TelenetWWW2' and int(Data['Status']) == 200:
            self.Get_oauth2_token()
        
        # OAUTH2 token successfully received leading to a successful login
        if not self.login_successful and Connection.Name == 'TelenetAPI' and int(Data['Status']) == 200:
            self.login_successful = True
            self.Get_Telemeter()
            
        # Get information from the Telemeter
        if self.login_successful and Connection.Name == 'TelenetAPI' and int(Data['Status']) == 200:
            Data_decoded = Data['Data'].decode('utf-8')
            #Domoticz.Debug(Data_decoded)
            if 'customer_number' not in Data_decoded:
                try:
                    self.telemeter_data = json.loads(Data_decoded)
                except:
                    pass
                else:
                    self.Handle_Telemeter()
                    # Anyway Telenet cuts the connections... So let us do it controlled
                    if self.httpConnWWW2.Connected():
                        self.httpConnWWW2.Disconnect()
                    if self.httpConnLogin.Connected():
                        self.httpConnLogin.Disconnect()
                    if self.httpConnAPI.Connected():
                        self.httpConnAPI.Disconnect()

        else:
            Domoticz.Debug("Error received on handling incoming messages!")
            TimeoutDevice(False, _UNIT_USAGE)

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
                
    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called (" + Connection.Name + ")")

    def onHeartbeat(self):
        self.runAgain -= 1
        if self.runAgain <= 0:

            if self.httpConnAPI.Connected():
                self.Get_Telemeter()
            else:
                self.httpConnAPI.Connect()
                
            # Run again following the period in the settings
            self.runAgain = _HOUR*float(Parameters["Mode5"].replace(',','.'))
                        
        else:
            Domoticz.Debug("onHeartbeat called, run again in "+str(self.runAgain)+" heartbeats.")

    def Handle_Telemeter(self):
        current_period = self.telemeter_data['internetusage'][0]['availableperiods'][0]
        current_volume = current_period['usages'][0]['totalusage']['wifree']
        if 'extendedvolume' in current_period['usages'][0]['totalusage']:
            current_volume += current_period['usages'][0]['totalusage']['extendedvolume']
        Domoticz.Debug("Current volume: {}".format(current_volume))
        current_volume = current_volume/1048576 #(1024*1024)
        UpdateDevice(_UNIT_USAGE, 0, '%.3f'%current_volume, Images[_IMAGE].ID)
            
    def Get_oauth2_token(self):
        if self.X_TOKEN_XSRF:
            headers = {
                'Host': 'api.prd.telenet.be',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
                'Accept': '*/*',
                'Connection': 'keep-alive',
                'x-alt-referer': 'https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice',
                'X-TOKEN-XSRF': self.X_TOKEN_XSRF,
                'Cookie': self.cookie
            }
        else:
            headers = {
                'Host': 'api.prd.telenet.be',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
                'Accept': '*/*',
                'Connection': 'keep-alive',
                'x-alt-referer': 'https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice'
            }
        url = '/ocapi/oauth/userdetails'
        Domoticz.Debug(TELENET_API)
        Domoticz.Debug(url)
        #Domoticz.Debug(json.dumps(headers))
        self.httpConnAPI.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})

    def Login(self):
        headers = {
            'Host': 'login.prd.telenet.be',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'Cookie': self.cookie
        }
        url = '/openid/oauth/authorize?client_id=ocapi&response_type=code&claims=%7B%22id_token%22:%7B%22http://telenet.be/claims/roles%22:%20null,%20%22http://telenet.be/claims/licenses%22:%20null%7D%7D&lang=nl&state=' + self.state + '&nonce=' + self.nonce + '&prompt=login'
        Domoticz.Debug(TELENET_LOGIN)
        Domoticz.Debug(url)
        #Domoticz.Debug(json.dumps(headers))
        self.httpConnLogin.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})
        
    def Login_Do(self):
        headers = {
            'Host': 'login.prd.telenet.be',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': self.cookie
        }
        data = "j_username={}&j_password={}&rememberme=True".format(Parameters["Mode1"], Parameters["Mode2"])
        url = '/openid/login.do'
        Domoticz.Debug(TELENET_LOGIN)
        Domoticz.Debug(url)
        #Domoticz.Debug(json.dumps(headers))
        self.httpConnLogin.Send({'Verb': 'POST', 'URL': url, 'Data': data, 'Headers': headers})

    def Get_Telemeter(self):
        headers = {
            'Host': 'api.prd.telenet.be',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'x-alt-referer': 'https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice',
            'X-TOKEN-XSRF': self.X_TOKEN_XSRF,
            'Cookie': self.cookie
        }
        #url = '/ocapi/public/?p=internetusage,internetusagereminder'
        url = '/ocapi/public/?p=internetusage'
        Domoticz.Debug(TELENET_API)
        Domoticz.Debug(url)
        #Domoticz.Debug(json.dumps(headers))
        #self.telemeter_data = ''
        self.httpConnAPI.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})

    def Redirect(self):
        url_parsed = urlparse(self.url_redirect)
        headers = {
            'Host': url_parsed.hostname,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive',
            'Cookie': self.cookie
        }
        url = url_parsed.path 
        if url_parsed.query:
            url += '?{}'.format(url_parsed.query)
        Domoticz.Debug(url_parsed.hostname)
        Domoticz.Debug(url)
        #Domoticz.Debug(json.dumps(headers))
        if TELENET_API in url_parsed.hostname:
            self.httpConnAPI.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})
        if TELENET_LOGIN in url_parsed.hostname:
            self.httpConnLogin.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})
        if TELENET_WWW2 in url_parsed.hostname:
            self.httpConnWWW2.Send({'Verb': 'GET', 'URL': url, 'Headers': headers})

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

################################################################################
# Generic helper functions
################################################################################

#DUMP THE PARAMETER
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))

#UPDATE THE DEVICE
def UpdateDevice(Unit, nValue, sValue, Image, TimedOut=0, AlwaysUpdate=False):
    if Unit in Devices:
        if Devices[Unit].nValue != int(nValue) or Devices[Unit].sValue != str(sValue) or Devices[Unit].TimedOut != TimedOut or Devices[Unit].Image != Image or AlwaysUpdate:
            Devices[Unit].Update(nValue=int(nValue), sValue=str(sValue), Image=Image, TimedOut=TimedOut)
            Domoticz.Debug("Update " + Devices[Unit].Name + ": " + str(nValue) + " - '" + str(sValue) + "'")
        else:
            Devices[Unit].Touch()

#SET DEVICE ON TIMED-OUT (OR ALL DEVICES)
def TimeoutDevice(All, Unit=0):
    if All:
        for x in Devices:
            UpdateDevice(x, Devices[x].nValue, Devices[x].sValue, Devices[x].Image, TimedOut=_TIMEDOUT)
    else:
        UpdateDevice(Unit, Devices[Unit].nValue, Devices[Unit].sValue, Devices[Unit].Image, TimedOut=_TIMEDOUT)

#CREATE ALL THE DEVICES (USED)
def CreateDevicesUsed():
    if (_UNIT_USAGE not in Devices):
        Domoticz.Device(Unit=_UNIT_USAGE, Name="Telemeter", TypeName="Custom", Options={"Custom": "0;GB"}, Image=Images[_IMAGE].ID, Used=1).Create()

#CREATE ALL THE DEVICES (NOT USED)
def CreateDevicesNotUsed():
    pass
    
#GET CPU TEMPERATURE
def getCPUtemperature():
    try:
        res = os.popen("cat /sys/class/thermal/thermal_zone0/temp").readline()
    except:
        res = "0"
    return round(float(res)/1000,1)
