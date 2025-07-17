from collections import defaultdict
from mavsdk import System
from mavsdk import mission_raw
from mavsdk import telemetry
import asyncio
import socket
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import math
import sys
import types
import json
import urllib
import threading
import datetime
import getpass
import configparser
import unicodedata
import string
import csv
import serial

#from tendo import singleton
# 
#me = singleton.SingleInstance()

config = configparser.ConfigParser()
if not os.path.exists('Dualem_companion.ini'):
    #config['EM'] = {'Mode': 'Serial', 'Address' : '/dev/ttyS0', 'Baud' : 38400}
    config['EM'] = {'Mode': 'Serial', 'Address' : '/dev/ttyUSB0', 'Baud' : 38400}
    config['Drone'] = {'system_address': 'udp://:14540'}
    #config['Drone'] = {'system_address': 'serial:///dev/ttyAGM0:58600'}

    config['Operator'] = {'Name' : getpass.getuser()}
    config['Output'] = {'Frequency' : 2, 'Directory' : '/media/qaafi/usb'}
    #config['Output'] = {'Frequency' : 2, 'Directory' : os.getcwd()}
    config['Dummy'] = {'active': True, 'dummyFile': 'Dualem21S_chickpea_14092023.csv'}
#    with open('Dualem_companion.ini', 'w') as configfile:
#        config.write(configfile)

else:
    config.read('Dualem_companion.ini')

lock = threading.Lock()

def dm(x):
    degrees = int(x) // 100
    minutes = x - 100*degrees
    return degrees, minutes

def decimal_degrees(degrees, minutes):
    return degrees + minutes/60 

def str_to_bool(s):
    if s == 'True':
         return True
    elif s == 'False':
         return False
    else:
         raise ValueError("Cannot convert {} to a bool".format(s)) 
    
# An IP6 server.
class HTTPServerV6(HTTPServer):
    address_family = socket.AF_INET6

# A mini http server
def MakeHandlerClassWithBakedInApp(app):
    class Handler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.emApp = app
            super().__init__(*args, **kwargs)
       
        def do_GET(self):
            if self.path.startswith("/getData"):
                since = -1
                try:
                    p = urllib.parse.urlparse(self.requestline)
                    q = dict(urllib.parse.parse_qsl(p.query.split(" ")[0]))
                    since = int(q['since'])
                except:
                        print("?since = " + self.requestline)
                        since = 0
                if (since >= 0):
                    self.getData( since )
            elif self.path.startswith("/setStatus"):
                newStatus = ""
                try:
                    p = urllib.parse.urlparse(self.requestline)
                    q = dict(urllib.parse.parse_qsl(p.query.split(" ")[0]))
                    newStatus = q['status']
                    self.setStatus( newStatus )
                except:
                    print("?newStatus = " + self.requestline)
            elif self.path.startswith("/shutDown"):  # fixme add a password to this
                doShutDown( )
            else:
                if self.path == "/":
                    self.path = "index.html"
                if self.path[0] == "/":
                    self.path = self.path[1:]

                path = os.getcwd() + "/CompanionHTML/" + os.path.normpath(self.path)

                if (os.path.isfile(path)):
                    mimetype = os.path.splitext(path)[1][1:]
                    if (mimetype == "js"):
                        mimetype = "javascript"
                    print("Sending " + path + " as " + mimetype)
                    self.send_response(200)
                    self.send_header("Content-type", "text/" + mimetype)
                    self.end_headers()
                    with open(path, "rb") as f:
                       self.wfile.write(f.read())
                    
                else:
                    print("Failed " + path + " as " + os.path.splitext(path)[1][1:])
                    self.send_response(404)

        def getData(self, since):
            result = {'data': self.emApp.getRecords(since), 'status': self.emApp.StatusInfo()}
            bData = bytes(json.dumps( result, ensure_ascii=False), 'utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write( bData )

        def setStatus(self, newStatus):
            bData = bytes(json.dumps(self.emApp.setStatus(newStatus), ensure_ascii=False), 'utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write( bData )

    return Handler

def doShutDown():
    os.system( "sudo /usr/sbin/shutdown -h +1")
    os._exit(1)

# watch for a new mission appearing
async def monitor_mission_changes(emApp, drone):
    async for change in drone.mission_raw.mission_changed():
        if change:
            await emApp.reloadMission(drone)
        else:
            print("-- No new mission")

# look out for "SPRAY" (216) events in the mission plan
async def monitor_mission_progress(emApp, drone):
   async for p in drone.mission_raw.mission_progress():
       if (emApp != None and p.current < len(emApp.mission_items)):
           print(f"Mission progress: "
               f"{p.current}/"
               f"{p.total}" + ", cmd=" + str(emApp.mission_items[p.current].command))
           if emApp.mission_items[p.current].command == 216:
               if(emApp.mission_items[p.current].param1 > 0):
                   emApp.Start()
               else:
                   emApp.Pause()

# Store away GPS position
async def monitor_gpsPos(emApp, drone):
   async for p in drone.telemetry.position():
       emApp.X1Val = p.longitude_deg
       emApp.Y1Val = p.latitude_deg 
       emApp.H1Val = p.absolute_altitude_m
       emApp.lastGPSTime = datetime.datetime.now()
       #print(f"drone: {p}")


# Store away GPS heading
async def monitor_gpsHead(emApp, drone):
   async for p in drone.telemetry.heading():
       emApp.TrackVal= p.heading_deg

# Store away velocity
async def monitor_gpsVelocity(emApp, drone):
   async for p in drone.telemetry.velocity_ned():
       emApp.SpeedVal= math.sqrt(p.north_m_s * p.north_m_s + p.east_m_s * p.east_m_s + p.down_m_s * p.down_m_s)

# Will likely always be RTK fixed - rover will stop if GPS disappears
async def monitor_gpsQuality(self, drone):
    async for p in drone.telemetry.gps_info():
        self.GPSQuality = str(p.fix_type)
        #print(f"drone: qlty: {p}")


################## Initialisation here ##################

class EMApp():
    def __init__(self):
        super().__init__()

        # Setting this flag will stop the reader threads
        self.stopFlag = threading.Event()
        self.restartEMFlag = threading.Event()

        self.numEMErrors = 0
        self.lastBellTime = datetime.datetime.now() #- datetime.timedelta(seconds=10)

        self.record = []

        # Default filenames
        today = datetime.datetime.now().strftime("%d-%m-%Y")
        self.saveFile = config['Output']['Directory'] + '/' + "EM.RootBot." + today + ".csv"  # fixme use mission name

        self.operator = config['Operator']['Name']
    
        self.X1Val = 0.0
        self.Y1Val = 0.0
        self.H1Val = 0.0
        self.GPSQuality = ""

        self.TrackVal= 0.0
        self.SpeedVal= 0.0
        self.EM_HCP0Val = 0.0
        self.EM_HCPI0Val = 0.0
        self.EM_PRP0Val = 0.0
        self.EM_PRPI0Val = 0.0
        self.EM_HCP1Val = 0.0
        self.EM_HCPI1Val = 0.0
        self.EM_PRP1Val = 0.0
        self.EM_PRPI1Val = 0.0
        self.EM_HCP2Val = 0.0
        self.EM_HCPI2Val = 0.0
        self.EM_PRP2Val = 0.0
        self.EM_PRPI2Val = 0.0
        self.EM_RollVal = 0
        self.EM_VoltsVal = 0
        self.EM_TemperatureVal = 0
        self.EM_PitchVal = 0
        self.EM_RollVal = 0

        # When set, fires a regular reading to the continuous file
        self.running = None

        self.errMsgText = ""
        self.errMsgSource = []
        self.lastErrorTime = datetime.datetime.now() - datetime.timedelta(seconds=30)

        self.errMsgSource = []

        self.workers = []
        if not str_to_bool(config['Dummy']['active']):
            self.EMThread = threading.Thread(target=self.em1_read, args=('EM',), daemon = True)
            self.EMThread.start()
            self.workers.append(self.EMThread)
        self.lastEMTime = datetime.datetime.now()
        self.lastGPSTime = datetime.datetime.now()

        self.MonitorThread = threading.Thread(target=self.startMonitor, args=('Monitor',), daemon = True)
        self.MonitorThread.start()
        self.workers.append(self.MonitorThread)

        self.HttpThread = threading.Thread(target=self.startHTTPServer, args=('http',), daemon = True)
        self.HttpThread.start()
        self.workers.append(self.HttpThread)

        self.droneState = 'disconnected'
        self.DroneThread = threading.Thread(target=self.startDrone, args=('local',), daemon = True)
        self.DroneThread.start()
        self.workers.append(self.DroneThread)

        # fixme - read from config file 
        self.writeOutput = "off"
        self.startLogging()

        for w in self.workers:
              w.join()

    # start continuous operation 
    def Start(self):
        self.writeOutput = "on"

    def Pause(self):
        self.writeOutput = "off"

    def Status(self):
        if (self.writeOutput == "off"):
            return("Paused")
        return("Running")

    def setStatus(self, newStatus):
        result = {"result" : 'ok'}
        if (newStatus == "Idle"):
            self.writeOutput = "off"
        elif (newStatus == "Running"):
            self.writeOutput = "on"
        else:
            result['result'] = "oops"
        return(result)

    def StatusInfo(self):
        result = {}
        result['status'] = "Running" if self.writeOutput == "on" else "Idle"
        result['EM'] = "Error" if self.hasEMError else "Ok"
        result['Drone'] = self.droneState
        
        return(result)

    def startLogging(self):
        if not os.path.exists(self.saveFile):
            with open(self.saveFile, 'w') as the_file:
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Longitude,Latitude,Elevation,Speed,Track,Quality,EM PRP0,EM PRP1,EM PRP2,EM HCP0,EM HCP1,EM HCP2,EM PRPI0,EM PRPI1,EM PRPI2,EM HCPI0,EM HCPI1,EM HCPI2,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=' + str(self.operator) + '\n')
        if (str_to_bool(config['Dummy']['active'])):
            self.setupDummy()
            self.doLoggingDummy()
        else:
            self.doLogging()

    def startMonitor(self, args):
        self.monitor = threading.Timer(0.250, self.doMonitor)
        self.monitor.start()

    def doMonitor(self):
        if (self.stopFlag.is_set()):
              return
        try:
            if (datetime.datetime.now() - self.lastErrorTime).total_seconds() > 10:
                while "EM" in self.errMsgSource: self.errMsgSource.remove("EM")

            if not self.hasEMError() and \
                    config['EM']['Mode'] != "Undefined" and \
                    (datetime.datetime.now() - self.lastEMTime).total_seconds() > 5:
                print("EM Timeout")
                self.errMsgSource.append("EM")
                self.restartEMFlag.set()

        except Exception as e:
            print("Monitor: " + e)
            pass

    def startHTTPServer(self, args):
       # ip6 will accept ip4 connections as well, provided it's not bound to
       # a specific v6 address
       webServer = HTTPServerV6(("::", 8080), MakeHandlerClassWithBakedInApp(self))
       print("Listening on http://" + webServer.server_address[0] + ":" + str(webServer.server_address[1]))

       try:
          webServer.serve_forever()
       except KeyboardInterrupt:
          pass
       webServer.server_close()


    def startDrone(self, args):
        print('drone: Connecting')
        asyncio.run(self.initDrone())

    async def initDrone(self):
        self.mission_task = None
        self.mission_items = []
        while True:
            drone = System()
            print("drone:  Waiting for connect at " + config['Drone']['system_address'])

            await drone.connect(system_address=config['Drone']['system_address'])
            async for state in drone.core.connection_state():
                if state.is_connected:
                    print("drone: Connected")
                    break

            self.droneState = 'connected'
            while True:
                print("drone: Monitoring telemetry")
                self.tasks = [] # async tasks monitoring mavlink
                bound_function = types.MethodType(monitor_gpsPos, self)
                self.tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_gpsHead, self)
                self.tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_gpsVelocity, self)
                self.tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_gpsQuality, self)
                self.tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_mission_changes, self)
                self.tasks.append(asyncio.ensure_future( bound_function(drone)))

                bound_function = types.MethodType(monitor_mission_progress, self)
                self.mission_task = asyncio.ensure_future( bound_function( drone ))

                try:
                    self.mission_items = await drone.mission_raw.download_mission()
                    print("-- Found mission of " + str(len(self.mission_items)) + " items")

                    self.tasks.append(self.mission_task)
                    while True:
                        async for state in drone.core.connection_state():
                            if not state.is_connected:
                                print("drone: disconnected")
                                self.droneState = 'disconnected'
                                break

                        async for p in drone.mission_raw.mission_progress():
                            if p.current >= p.total:
                                print("-- Mission is finished")
                                self.mission_task.cancel()
                            else:
                                print("-- mission at step " + str(p.current))

                        #print("-- Idle")
                        #time.sleep(0.5)
                        await asyncio.sleep(0.5)
                except Exception as err:
                    print(f"drone: Unexpected {err=}, {type(err)=}")
                    # fixme - unsure what will happen when the drone disconnects?
                finally:
                    for t in self.tasks:
                        t.cancel()
                    print("drone: Unwound callbacks")


    async def reloadMission(self, drone):
        if (len(self.mission_items) > 0): print("drone: Abandoning old mission")

        while(len(self.mission_items) > 0):
            self.mission_items.pop()
        
        self.mission_items = await drone.mission_raw.download_mission()
        print("drone: Got new mission of " + str(len(self.mission_items)) + " items")

        self.mission_task.cancel()
        bound_function = types.MethodType(monitor_mission_progress, self)
        self.mission_task = asyncio.ensure_future( bound_function(drone))
        #tasks.append(mission_task)

    # Logging loop
    def doLogging(self):
        t0 = datetime.datetime.now()
        self.doit()
        OutputFrequency = 2.0
        try:
            OutputFrequency = float(self.OutputFrequency)
        except:
            pass
        if (OutputFrequency <= 0):
            OutputFrequency = 2
        freqMs = 1000.0 * 1.0 / OutputFrequency
        delayMs = 0
        t1 = t0 + datetime.timedelta(milliseconds=freqMs)
        if (t1 > datetime.datetime.now()):
            delayDt =  t1 - datetime.datetime.now()
            delayMs = max(0, int(delayDt.total_seconds() * 1000.0))
             
        self.running = threading.Timer(delayMs / 1000.0, self.doLogging)  
        self.running.start()

    def shutDown(self):
        self.saveConfig()
        self.stopFlag.set()
        sys.exit(0)

    def hasEMError (self):
        return "EM" in self.errMsgSource

    def getE1(self):
        with lock:
              return("," + str(self.EM_PRP0Val) + "," + str(self.EM_PRP1Val) + "," + str(self.EM_PRP2Val) +  \
                       "," + str(self.EM_HCP0Val) + "," + str(self.EM_HCP1Val) + "," + str(self.EM_HCP2Val) +  \
                     "," + str(self.EM_PRPI0Val) + "," + str(self.EM_PRPI1Val) + "," + str(self.EM_PRPI2Val) +  \
                     "," + str(self.EM_HCPI0Val) + "," + str(self.EM_HCPI1Val) + "," + str(self.EM_HCPI2Val) +  \
                     "," + str(self.EM_VoltsVal) + "," + str(self.EM_TemperatureVal) + \
                     "," + str(self.EM_PitchVal) + "," + str(self.EM_RollVal))

    def doLoggingDummy(self):
        t0 = datetime.datetime.now()
        self.doitDummy()
        OutputFrequency = 2.0
        try:
            OutputFrequency = float(self.OutputFrequency)
        except:
            pass
        if (OutputFrequency <= 0):
            OutputFrequency = 2
        freqMs = 1000.0 * 1.0 / OutputFrequency
        delayMs = 0
        t1 = t0 + datetime.timedelta(milliseconds=freqMs)
        if (t1 > datetime.datetime.now()):
            delayDt =  t1 - datetime.datetime.now()
            delayMs = max(0, int(delayDt.total_seconds() * 1000.0))
             
        self.running = threading.Timer(delayMs / 1000.0, self.doLoggingDummy)  
        self.running.start()

    def doitDummy(self):
        self.recordPoint(self.dummyData['YYYY-MM-DD'][self.dummyCtr] +',' + self.dummyData['HH:MM:SS.F'][self.dummyCtr], 
            self.writeOutput == "on", 
            self.dummyData['Longitude 2'][self.dummyCtr], self.dummyData['Latitude 2'][self.dummyCtr],self.dummyData['Elevation 2'][self.dummyCtr],
            self.dummyData['Speed 2'][self.dummyCtr], self.dummyData['Track 2'][self.dummyCtr], 'Unknown',
            self.dummyData['EM PRPH'][self.dummyCtr],self.dummyData['EM PRP1'][self.dummyCtr], self.dummyData['EM PRP2'][self.dummyCtr], 
            self.dummyData['EM HCPH'][self.dummyCtr],self.dummyData['EM HCP1'][self.dummyCtr], self.dummyData['EM HCP2'][self.dummyCtr],
            self.dummyData['EM PRPIH'][self.dummyCtr],self.dummyData['EM PRPI1'][self.dummyCtr], self.dummyData['EM PRPI2'][self.dummyCtr], 
            self.dummyData['EM HPCIH'][self.dummyCtr],self.dummyData['EM HCPI1'][self.dummyCtr], self.dummyData['EM HCPI2'][self.dummyCtr],
            self.dummyData['EM Volts'][self.dummyCtr],self.dummyData['EM Temperature'][self.dummyCtr],self.dummyData['EM Pitch'][self.dummyCtr], self.dummyData['EM Roll'][self.dummyCtr])
        self.dummyCtr = self.dummyCtr + 1


    def setupDummy(self):
        self.dummyCtr = 0
        self.dummyData = {}
        with open(config['Dummy']['dummyFile'], 'r') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"', skipinitialspace=True)
            header = reader.__next__()
            for name in header:
                self.dummyData[name] = []
            # read rows, append values to lists
            for row in reader:
                for i, value in enumerate(row):
                    self.dummyData[header[i]].append(value)



    # Write to the continuous output file 
    def doit(self):
        time_now = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S.%f')
        if (self.writeOutput == "on"):
            line = time_now +  "," + \
                str(self.X1Val) + "," + str(self.Y1Val) + "," + str(self.H1Val) + "," + \
                str(self.SpeedVal) + "," + str(self.TrackVal) + "," + self.GPSQuality +\
                    self.getE1() + \
                    '\n'
            with open(self.saveFile, 'a') as the_file:
                the_file.write(line)
                the_file.flush()
        self.recordPoint(time_now, self.writeOutput == "on", 
                         self.X1Val, self.Y1Val, self.H1Val,
                         self.SpeedVal, self.TrackVal, self.GPSQuality,
                         self.EM_PRP0Val,self.EM_PRP1Val, self.EM_PRP2Val, 
                         self.EM_HCP0Val,self.EM_HCP1Val, self.EM_HCP2Val,
                         self.EM_PRPI0Val,self.EM_PRPI1Val, self.EM_PRPI2Val, 
                         self.EM_HCPI0Val,self.EM_HCPI1Val, self.EM_HCPI2Val,
                         self.EM_VoltsVal, self.EM_TemperatureVal, self.EM_PitchVal, self.EM_RollVal)
        

    def recordPoint(self, time, recorded, X, Y, Z, Speed, Track, Quality, 
                    EM_PRP0, EM_PRP1, EM_PRP2, 
                    EM_HCP0, EM_HCP1, EM_HCP2,
                    EM_PRPI0, EM_PRPI1, EM_PRPI2, 
                    EM_HCPI0, EM_HCPI1, EM_HCPI2,
                    EM_Volts, EM_Temperature, EM_Pitch, EM_Roll):
        self.record.append({'id': len(self.record),
                         'timestamp': time,
                         'recorded': recorded,
                         'X': X,
                         'Y': Y,
                         'Z': Z,
                         'Speed': Speed, 
                         'Track': Track, 
                         'Quality': Quality,
                         'EM_PRP0': EM_PRP0,
                         'EM_PRP1': EM_PRP1, 
                         'EM_PRP2': EM_PRP2, 
                         'EM_HCP0': EM_HCP0,
                         'EM_HCP1': EM_HCP1, 
                         'EM_HCP2': EM_HCP2,
                         'EM_PRPI0': EM_PRPI0,
                         'EM_PRPI1': EM_PRPI1, 
                         'EM_PRPI2': EM_PRPI2, 
                         'EM_HCPI0': EM_HCPI0,
                         'EM_HCPI1': EM_HCPI1, 
                         'EM_HCPI2': EM_HCPI2,
                         'EM_Volts': EM_Volts, 
                         'EM_Temperature': EM_Temperature, 
                         'EM_Pitch': EM_Pitch,
                         'EM_Roll': EM_Roll})

    # return the last records since since.
    def getRecords(self, since):
        res = []
        last = len(self.record) - 1
        while last >= 0:
            if self.record[last]['id'] > since:
                res.append(self.record[last])
            else:
                break
            last = last - 1
        print("returning " + str(len(res)) + " records")
        res.reverse()
        return(res)

    def openComms(self, cfg):
        print("Opening " + cfg['Mode'] + ' ' + cfg['Address'])
        s = self.openCommsReal(cfg)
        if (hasattr(s, "write")):
            try: 
                s.write(b'%\r\n') # Sometimes this is needed, sometimes not...
            except:
                pass
            finally:
                s.close()
            s = self.openCommsReal(cfg)
        print("OK")
        return s

    def openCommsReal(self, cfg):
        if (cfg['Mode'] == "Bluetooth"):
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            btName = cfg['Address']
            btAddr = ""
            for addr, name in self.BTPortDescriptions.items(): 
                if name == btName:
                    btAddr = addr
            #print ("connecting to BT=" + btAddr)
            s.connect((btAddr, 1))
            s.setblocking(0)
            s.settimeout(5)

        elif (cfg['Mode'] == "IP"):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            hp = cfg['Address'].split(":")
            host = str(hp[0])
            if (len(hp) > 1):
                port = int(hp[1])
            else:
                port = 1
            s.connect((host, port))
            s.setblocking(0)
            s.settimeout(5)

        elif (cfg['Mode'] == "Serial"):
            port = cfg['Address']
            baudrate = int(cfg['Baud'])
            s = serial.Serial(port, baudrate= baudrate, timeout=5, write_timeout=5)
        else:
            raise Exception("Unknown mode '" + cfg['Mode'] + "'")
        return s

    # Decode a nmea string and set the associated TCL variable
    def nmea_decode(self, linedata, useGPS = True):
        splitlines = linedata.split(',')
        #print(splitlines)
        if useGPS and len(splitlines) >= 10 and ("GPGGA" in splitlines[0] or "GNGGA" in splitlines[0]):
            S = decimal_degrees(*dm(float(splitlines[2])))
            if splitlines[3].find('S') >= 0:
                S = S * -1
            E = decimal_degrees(*dm(float(splitlines[4])))
            H = float(splitlines[9])
            Q = int(splitlines[6])
            with lock:
                self.X1Val = E
                self.Y1Val = S
                self.H1Val = H
                self.GPSQuality = Q
            return 1
        elif useGPS and len(splitlines) >= 8 and "GPVTG" in splitlines[0]: # http://aprs.gids.nl/nmea/#vtg
            T = 0.0
            if splitlines[1] != "":
                T = float(splitlines[1])
                S = 0.0
            if splitlines[7] != "":
                S = float(splitlines[7])
                with lock:
                    self.TrackVal = T
                    self.SpeedVal = S
            return 1
        elif len(splitlines) >= 6 and ("PDLM0" in splitlines[0] or "PDLMH" in splitlines[0]):
            with lock:
                self.EM_HCP0Val = splitlines[2]   #HCP conductivity in mS/m
                self.EM_HCPI0Val = splitlines[3]  #HCP inphase in ppt
                self.EM_PRP0Val = splitlines[4]   #PRP conductivity in mS/m
                self.EM_PRPI0Val = splitlines[5].split('*')[0] #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 6 and "PDLM1" in splitlines[0]:
            with lock:
                self.EM_HCP1Val = splitlines[2]   #HCP conductivity in mS/m
                self.EM_HCPI1Val = splitlines[3]  #HCP inphase in ppt
                self.EM_PRP1Val = splitlines[4]   #PRP conductivity in mS/m
                self.EM_PRPI1Val = splitlines[5].split('*')[0] #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 6 and "PDLM2" in splitlines[0]:
            with lock:
                self.EM_HCP2Val = splitlines[2]      #HCP conductivity in mS/m
                self.EM_HCPI2Val = splitlines[3]     #HCP inphase in ppt
                self.EM_PRP2Val = splitlines[4]      #PRP conductivity in mS/m
                self.EM_PRPI2Val = splitlines[5].split('*')[0]      #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 4 and "PDLMA" in splitlines[0]:
            with lock:
                self.EM_VoltsVal = float(splitlines[1])
                self.EM_TemperatureVal = float(splitlines[2])
                self.EM_PitchVal = float(splitlines[3])
                self.EM_RollVal = float(splitlines[4].split('*')[0])
            return 1
        return 0

    # The em reader thread
    def em1_read(self, cfgName):
        while not self.stopFlag.is_set():
            cfg = config[cfgName]
            self.lastEMTime = datetime.datetime.now()
            if (cfg['Mode'] != "Undefined"):
                self.restartEMFlag.clear()
                while "EM" in self.errMsgSource: self.errMsgSource.remove("EM")
                self.EM_HCP0Val = 0.0
                self.EM_HCPI0Val = 0.0
                self.EM_PRP0Val = 0.0
                self.EM_PRPI0Val = 0.0
                self.EM_HCP1Val = 0.0
                self.EM_HCPI1Val = 0.0
                self.EM_PRP1Val = 0.0
                self.EM_PRPI1Val = 0.0
                self.EM_HCP2Val = 0.0
                self.EM_HCPI2Val = 0.0
                self.EM_PRP2Val = 0.0
                self.EM_PRPI2Val = 0.0
                self.EM_RollVal = 0
                self.EM_VoltsVal = 0
                self.EM_TemperatureVal = 0
                self.EM_PitchVal = 0
                self.EM_RollVal = 0
                s = None
                try:
                    s = self.openComms(cfg)
                    line = ''
                    while (not self.stopFlag.is_set()) and not self.restartEMFlag.is_set():
                        while (line.find('\n') < 0) and not self.restartEMFlag.is_set():
                            if (cfg['Mode'] == "Serial"):
                                if (s.in_waiting > 0):
                                    line = line + s.read(s.in_waiting).decode('ascii') 
                                if (s.in_waiting <= 0):
                                    time.sleep(0.01) 
                            else:
                                try:
                                    line += str(s.recv(1), 'ascii')  # BT, IP socket - has timeout set
                                except socket.timeout as e:
                                    err = e.args[0]
                                    # this next if/else is a bit redundant, but illustrates how the
                                    # timeout exception is setup
                                    if err == 'timed out':
                                        time.sleep(1)
                                        print("em timeout detected")
                                        continue
                                    else:
                                        raise e

                        linedata = line[:line.find('\n')]
                        line = line[line.find('\n')+1:]
                        
                        if self.nmea_decode(linedata, useGPS=False): 
                            self.lastEMTime = datetime.datetime.now()

                        ROLL = self.EM_RollVal
                        if float(abs(ROLL)) > 20:
                            print(' Roll angle: ' + str(ROLL))
                            self.errMsgSource.append("EM")

                        #print("stop= " + str(self.stopFlag.is_set()) + "," + "restart= " + str( self.restartEMFlag.is_set()))
                    # end while    
                except Exception as e:
                    print(" EM: " + str(e))
                    #self.showMessage("Cant open " + cfg['Address'] )
                    self.errMsgSource.append("EM")
                    pass
                if (s is not None):
                    s.close()
            time.sleep(1)

app = None
def main():
    app = EMApp()
if __name__ == '__main__':
    main()
