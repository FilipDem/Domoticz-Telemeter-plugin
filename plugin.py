#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Telenet Python Plugin
#
# Author: Filip Demaertelaere
#
# Plugin to get the download volume for Telenet
#
"""
<plugin key="Telenet" name="Telenet" author="Filip Demaertelaere" version="3.0.0">
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
import sys, os
major,minor,x,y,z = sys.version_info
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.append('/usr/local/lib/python{}.{}/dist-packages'.format(major, minor))
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from domoticz_tools import *
import Domoticz
import Telenet
import threading
import queue
import time

#DEFAULT IMAGE
_IMAGE = 'Telenet'

#THE HAERTBEAT IS EVERY 10s
_HOUR = MINUTE*60

################################################################################
# Start Plugin
################################################################################

class BasePlugin:

    def __init__(self):
        self.debug = DEBUG_OFF
        self.runAgain = MINUTE
        self.Login = False
        self.ErrorLevel = 0
        self.MyTelenet = None
        self.tasksQueue = queue.Queue()
        self.tasksThread = threading.Thread(name='QueueThread', target=BasePlugin.handleTasks, args=(self,))

    def onStart(self):
        Domoticz.Debug('onStart called')

        # Debugging On/Off
        self.debug = DEBUG_ON if Parameters['Mode6'] == 'Debug' else DEBUG_OFF
        Domoticz.Debugging(self.debug)
        if self.debug == DEBUG_ON:
            DumpConfigToLog(Parameters, Devices)
        
        # Check if images are in database
        if _IMAGE not in Images:
            Domoticz.Image('Telenet.zip').Create()

        # Timeout all devices
        TimeoutDevice(Devices, All=True)
        
        # Start thread
        self.MyTelenet = Telenet.Telenet(Parameters['Mode1'], Parameters['Mode2'])
        self.tasksThread.start()
        self.tasksQueue.put({'Action': 'Login'})

    def onStop(self):
        Domoticz.Debug('onStop called')
        
        # Signal queue thread to exit
        self.tasksQueue.put(None)
        self.tasksThread.join()

        # Wait until queue thread has exited
        Domoticz.Debug('Threads still active: {} (should be 1)'.format(threading.active_count()))
        endTime = time.time() + 70
        while (threading.active_count() > 1) and (time.time() < endTime):
            for thread in threading.enumerate():
                if thread.name != threading.current_thread().name:
                    Domoticz.Debug('Thread {} is still running, waiting otherwise Domoticz will abort on plugin exit.'.format(thread.name))
            time.sleep(1.0)

        Domoticz.Debug('Plugin stopped')

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug('onConnect called ({}) with status={}'.format(Connection.Name, Status))

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called: {} - {}".format(Connection.Name, Data['Status']))

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug('onCommand called for Unit: {} - Parameter: {} - Level: {}'.format(Unit, Command, Level))
                
    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug('Notification: {}, {}, {}, {}, {}, {}, {}'.format(
            Name, Subject, Text, Status, Priority, Sound, ImageFile
        ))

    def onDisconnect(self, Connection):
        Domoticz.Debug('onDisconnect called ({})'.format(Connection.Name))

    def onHeartbeat(self):
        self.runAgain -= 1
        if self.runAgain <= 0:

            self.tasksQueue.put({'Action': 'GetInternetVolume'})
            if self.ErrorLevel == 3:
                TimeoutDevice(Devices, All=True)
                Domoticz.Error('Unable to get data from Telenet.')
            if self.ErrorLevel and not self.ErrorLevel % 2:
                self.tasksQueue.put({'Action': 'Login'})
                
            self.runAgain = _HOUR*float(Parameters['Mode5'].replace(',','.'))

    # Thread to handle the messages
    def handleTasks(self):
        try:
            Domoticz.Debug('Entering tasks handler')
            while True:
                task = self.tasksQueue.get(block=True)
                if task is None:
                    Domoticz.Debug('Exiting task handler')
                    try:
                        self.MyTelenet.close()
                    except AttributeError:
                        pass
                    self.tasksQueue.task_done()
                    break

                Domoticz.Debug('Handling task: {}.'.format(task['Action']))
                if task['Action'] == 'Login':
                    self.Login = False
                    if self.MyTelenet.login() and self.MyTelenet.get_user_data():
                        self.Login = True
                    else:
                        self.ErrorLevel += 1
                        Domoticz.Error('Unable to login on MyTelenet with defined hardware settings or no contract data found.')
                        
                elif task['Action'] == 'GetInternetVolume':
                    if self.Login and self.MyTelenet.login() and self.MyTelenet.get_user_data():
                        if self.MyTelenet.telemeter():
                            for Contract in self.MyTelenet.telemeter_info:
                                Unit = FindUnitFromName(Devices, Parameters, Contract['municipality'])
                                if not Unit:
                                    Unit = GetNextFreeUnit(Devices)
                                    description = CreateDescription(Contract['businessidentifier'])
                                    Domoticz.Device(Unit=Unit, Name=Contract['municipality'], Description=description, TypeName="Custom", Options={"Custom": "0;GB"}, Image=Images[_IMAGE].ID, Used=1).Create()
                                    TimeoutDevice(Devices, Unit=Unit)
                                if 'total_usage_gb' in Contract:
                                    UpdateDevice(False, Devices, Unit, 0, '%.3f' % Contract['total_usage_gb'])
                                    Domoticz.Debug('Telenet Usage: {}'.format(Contract['total_usage_gb']))
                                    self.ErrorLevel = 0
                            else:
                                self.ErrorLevel += 1
                        else:
                            self.ErrorLevel += 1
                    else:
                        self.ErrorLevel += 1

                else:
                    Domoticz.Error('TaskHandler: unknown action code {}'.format(task['Action']))

                Domoticz.Debug('Finished handling task: {}.'.format(task['Action']))
                self.tasksQueue.task_done()

        except Exception as err:
            Domoticz.Error('General error TaskHandler: {}'.format(err))
            # For debugging
            import traceback
            Domoticz.Debug('Login error TRACEBACK: {}'.format(traceback.format_exc()))
            with open('{}Telenet_traceback.txt'.format(Parameters['HomeFolder']), "a") as myfile:
                myfile.write('{}'.format(traceback.format_exc()))
                myfile.write('---------------------------------\n')
            self.tasksQueue.task_done()


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
# Specific helper functions
################################################################################
