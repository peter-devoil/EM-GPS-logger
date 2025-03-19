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
import threading
import datetime
import getpass
import configparser

#from tendo import singleton
# 
#me = singleton.SingleInstance()

config = configparser.ConfigParser()
if not os.path.exists('Dualem_companion.ini'):
    #config['EM'] = {'Mode': 'Serial', 'Address' : '/dev/ttyS0', 'Baud' : 38400}
    config['EM'] = {'Mode': 'Undefined', 'Address' : '/dev/ttyS0', 'Baud' : 38400}
    #config['Drone'] = {'system_address': 'udp://:14540'}
    config['Drone'] = {'system_address': 'serial:///dev/ttyAGM0:58600'}

    config['Operator'] = {'Name' : getpass.getuser()}
    config['Output'] = {'Frequency' : 2, 'Directory' : '/media/qaafi/usb'}

    with open('Dualem_companion.ini', 'w') as configfile:
        config.write(configfile)

else:
    config.read('Dualem_companion.ini')

lock = threading.Lock()

def dm(x):
    degrees = int(x) // 100
    minutes = x - 100*degrees
    return degrees, minutes

def decimal_degrees(degrees, minutes):
    return degrees + minutes/60 

def MakeHandlerClassWithBakedInApp(app):
   class Handler(BaseHTTPRequestHandler):
       def __init__(self, *args, **kwargs):
          self.emApp = app
          super().__init__(*args, **kwargs)
       
       def do_GET(self):
          self.send_response(200)
          self.send_header("Content-type", "text/html")
          self.end_headers()
          self.wfile.write(bytes("<html><head><title>Robot Companion</title></head>", "utf-8"))
          self.wfile.write(bytes("<body>", "utf-8"))
          self.wfile.write(bytes("Status:<br/>" + self.emApp.StatusInfo() + "<br/>","utf-8"))
          self.wfile.write(bytes("</body></html>", "utf-8"))

   return Handler

# look out for "SPRAY" (216) events in the mission plan
async def monitor_mission_progress(emApp, drone, mission_items):
   async for p in drone.mission_raw.mission_progress():
       if (p.current < len(mission_items)):
           print(f"Mission progress: "
               f"{p.current}/"
               f"{p.total}" + ", cmd=" + str(mission_items[p.current].command))
           if emApp != None and mission_items[p.current].command == 216:
               if(mission_items[p.current].param1 > 0):
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

# Store away GPS heading
async def monitor_gpsHead(emApp, drone):
   async for p in drone.telemetry.heading():
       emApp.TrackVal= p.heading_deg

# Store away velocity
async def monitor_gpsVelocity(emApp, drone):
   async for p in drone.telemetry.velocityned():
       emApp.SpeedVal= math.sqrt(p.north_m_s * p.north_m_s + p.east_m_s * p.east_m_s + p.down_m_s * p.down_m_s)

# Will likely always be RTK fixed - rover will stop if GPS disappears
async def monitor_gpsQuality(emApp, drone):
   async for p in drone.telemetry.gpsinfo():
       emApp.GPSQuality = str(p.fix_type)


################## Initialisation here ##################

class EMApp():
    def __init__(self):
        super().__init__()

        # Setting this flag will stop the reader threads
        self.stopFlag = threading.Event()
        self.restartEMFlag = threading.Event()

        self.numEMErrors = 0
        self.lastBellTime = datetime.datetime.now() #- datetime.timedelta(seconds=10)
    
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
        self.EM_VoltsVal= 0.0
        self.EM_PitchVal= 0.0
        self.EM_RollVal= 0.0

        # When set, fires a regular reading to the continuous file
        self.running = None

        self.errMsgText = ""
        self.errMsgSource = []
        self.lastErrorTime = datetime.datetime.now() - datetime.timedelta(seconds=30)

        self.errMsgSource = []

        self.workers = []
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

        self.DroneThread = threading.Thread(target=self.startDrone, args=('local',), daemon = True)
        self.DroneThread.start()
        self.workers.append(self.DroneThread)

        for w in self.workers:
              w.join()

    # toggle continuous operation on/off
    def Start(self):
        if (self.running == None):
            self.startLogging()

    def Pause(self):
        if (self.running != None):
            self.running = None

    def Status(self):
        if (self.running == None):
            return("Paused")
        return("Running")
        
    def StatusInfo(self):
        # fixme add drone info here
        if (self.running != None):
            return("EM: " + ("Error" if self.hasEMError else "Ok"))
        return("Idle")

    def startLogging(self):
        if not os.path.exists(self.saveFile):
            with open(self.saveFile, 'w') as the_file:
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Longitude,Latitude,Elevation,Speed,Track,Quality,EM PRP0,EM PRP1,EM PRP2,EM HCP0,EM HCP1,EM HCP2,EM PRPI0,EM PRPI1,EM PRPI2,EM HCPI0,EM HCPI1,EM HCPI2,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=' + str(self.operator) + '\n')
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
       hostName = ""
       serverPort = 8080
       webServer = HTTPServer((hostName, serverPort), MakeHandlerClassWithBakedInApp(self))
       print("Listening on http://%s:%s" % (hostName, serverPort))

       try:
          webServer.serve_forever()
       except KeyboardInterrupt:
          pass
       webServer.server_close()


    def startDrone(self, args):
        print('Connecting to drone')
        asyncio.run(self.initDrone())
        
    async def initDrone(self):
        while True:
            drone = System()
            print("Waiting for drone to connect at " + config['Drone']['system_address'])

            await drone.connect(system_address=config['Drone']['system_address'])
            async for state in drone.core.connection_state():
                if state.is_connected:
                    print("-- Connected to drone!")
                    break

            while True:
                print("-- Waiting for a new mission")
                tasks = [] # async tasks monitoring mavlink
                bound_function = types.MethodType(monitor_gpsPos, self)
                tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_gpsHead, self)
                tasks.append(asyncio.ensure_future( bound_function(drone) ))

                bound_function = types.MethodType(monitor_gpsVelocity, self)
                tasks.append(asyncio.ensure_future( bound_function(drone) ))

                try:
                    mission_items = await drone.mission_raw.download_mission()
                    print("-- Found mission of " + str(len(mission_items)) + " items")

                    bound_function = types.MethodType(monitor_mission_progress, self)
                    mission_task = asyncio.ensure_future( bound_function(drone, mission_items))
                    tasks.append(mission_task)
                    while True:
                        async for change in drone.mission_raw.mission_changed():
                            if change:
                                print("-- Abandoning old mission")
                                mission_task.cancel()
                                tasks.pop() # mission is always last task
                                mission_items = await drone.mission_raw.download_mission()
                                print("-- Got new mission of " + str(len(mission_items)) + " items")
                                bound_function = types.MethodType(monitor_mission_progress, self)
                                mission_task = asyncio.ensure_future( bound_function(drone, mission_items))
                                tasks.append(mission_task)

                        async for p in drone.mission_raw.mission_progress():
                            if p.current >= p.total:
                                print("-- Mission is finished")
                                mission_task.cancel()

                        time.sleep(0.5)
                except Exception as err:
                    print(f"Unexpected {err=}, {type(err)=}")
                    # fixme - unsure what will happen when the drone disconnects?
                finally:
                    for t in tasks:
                        t.cancel()
                    print("Unwound drone callbacks")

    # Logging callbacks
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

    # Write to the continuous output file 
    def doit(self):
        time_now = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S.%f')
        line = time_now +  "," + \
            str(self.X1Val) + "," + str(self.Y1Val) + "," + str(self.H1Val) + "," + \
            str(self.SpeedVal) + "," + str(self.TrackVal) + "," + self.GPSQuality +\
                self.getE1() + \
                '\n'
        with open(self.saveFile, 'a') as the_file:
            the_file.write(line)
            the_file.flush()
        self.markTrack(self.X1Val, self.Y1Val)
        self.recordEM(self.EM_PRP0Val,self.EM_PRP1Val, self.EM_PRP2Val, 
                      self.EM_HCP0Val,self.EM_HCP1Val, self.EM_HCP2Val)

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
