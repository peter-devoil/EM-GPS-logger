import serial
import socket
from serial.tools import list_ports
import os
import sys
import subprocess
import time
import threading
import datetime
import getpass
import configparser


#from tendo import singleton

import tkinter as tk
from tkinter import ttk

# 
#me = singleton.SingleInstance()

# Use Windows Device Manager to find ports on each system
config = configparser.ConfigParser()
if not os.path.exists('Dualem_and_GPS_datalogger.ini'):
    #config['GPS1'] = {'Mode': 'Undefined', 'Address': '10.0.0.1:5017'}
    config['GPS1'] = {'Mode': 'Bluetooth', 'Address' : 'Sparkfun Facet'}
    config['EM'] = {'Mode': 'Serial', 'Address' : '/dev/ttyS0'}
    #config['EM'] = {'Mode': 'Undefined', 'Port': 'Undefined', 'Baud': 38400} # COM4
    config['Operator'] = {'Name' : getpass.getuser()}
else:
    config.read('Dualem_and_GPS_datalogger.ini')

def saveConfig ():
    with open('Dualem_and_GPS_datalogger.ini', 'w') as configfile:
        config.write(configfile)

lock = threading.Lock()

def dm(x):
    degrees = int(x) // 100
    minutes = x - 100*degrees
    return degrees, minutes

def decimal_degrees(degrees, minutes):
    return degrees + minutes/60 

comPortDescriptions = {}
BTPortDescriptions = {}

def checkComPorts():
    comPortDescriptions.clear()
    comPortDescriptions['Undefined'] = "Undefined"
    try:
       for port in list_ports.comports():
           comPortDescriptions[port.device] = port.description
    except:
        #print("Exception finding com ports")
        pass
    #comPortDescriptions['COM1'] = "Sample com 1 L57"
    #comPortDescriptions['COM6'] = "Sample com 6 L58"

def checkBTPorts():
    BTPortDescriptions.clear()
    BTPortDescriptions["Undefined"] = "Undefined"

# fixme may need Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

    args = ["powershell.exe",  "-ExecutionPolicy", "RemoteSigned", "-Command", r"-"]
    process = subprocess.Popen(args, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
    process.stdin.write(b"$bluetoothDevices = Get-WmiObject -Query \"SELECT * FROM Win32_PnPEntity WHERE PNPClass = 'Bluetooth'\" | Select-Object Name,HardwareID\r\n")
    process.stdin.write(b"foreach ($device in $bluetoothDevices) {  Write-Host \"$($device.Name),$($device.HardwareID)\" }\r\n")

    output = process.communicate()[0].decode("utf-8").split("\n")
    #print(output)
    for line in output:
        try:
            splitLn = line.split(",")
            name = splitLn[0]
            addr = splitLn[1]
            if (addr.startswith("BTHENUM\\Dev_")):
                addr = addr[12:]
                s = addr[0:2] + ":" + addr[2:4] + ":" + addr[4:6] + ":" + \
                          addr[6:8] + ":" + addr[8:10] + ":" + addr[10:12] 
                BTPortDescriptions[s] = name
        except:
            pass
    
    #BTPortDescriptions['b8:d6:1a:0d:9a:22'] = "Sparkfun Facet"
    BTPortDescriptions['dd:ee:ff:aa:bb:cc'] = "Sample BT 1 (garbage)"


def getAddresses( currentMode ):
    if (currentMode == "IP"):
        return(getIPAddresses())
    if (currentMode == "Serial"):
        return(getSerialAddresses())
    if (currentMode == "Bluetooth"):
        return(getBTAddresses())
    return([])

def getBTAddresses():
    result = []
    for addr, name in BTPortDescriptions.items():
        result.append(name)
        
    return(result)

def getSerialAddresses():
    result = []
    for addr, name in comPortDescriptions.items():
        result.append(addr)

    return(result)

def getIPAddresses():
    return ['10.0.0.1:5017'] # fixme need to store each in .ini file
################## Initialisation here ##################

class EMApp(ttk.Frame):
    def __init__(self):
        super().__init__()
        self.initUI()

        # Setting this flag will stop the reader threads
        self.stopFlag = threading.Event()
        self.restartEMFlag = threading.Event()
        self.restartGPS1Flag = threading.Event()

        self.workers = []
        self.thread1 = threading.Thread(target=self.gps1_read, args=('GPS1',), daemon = True)
        self.thread1.start()
        self.workers.append(self.thread1)
        self.lastGPS1Time = datetime.datetime.now()

        self.EMThread = threading.Thread(target=self.em1_read, args=('EM',), daemon = True)
        self.EMThread.start()
        self.workers.append(self.EMThread)
        self.lastEMTime = datetime.datetime.now()

        self.numGPSErrors = 0
        self.numEMErrors = 0
        self.lastBellTime = datetime.datetime.now() #- datetime.timedelta(seconds=10)
    
    def IPHostCallback (self, variable):
        if ":" in config['GPS1']["Address"]:
            config['GPS1']["Address"] = variable.get() + ":" + config['GPS1']["Address"].split(":")[1]
        else:
            config['GPS1']["Address"] = variable.get()

    def IPPortCallback (self, variable):
        config['GPS1']["Address"] = config['GPS1']["Address"].split(":")[0] + ":" + variable.get()

    # Build the UI
    def initUI(self):
        global config
        self.master.title("EM")

        self.style = ttk.Style()
        self.style.configure('CommError.TFrame', background="red", foreground="white")
        self.style.configure('CommOK.TFrame', background=root.cget("bg"), foreground="black")
        self.style.configure('CommError.TLabel', background="red", foreground="white" )
        self.style.configure('CommOK.TLabel', background=root.cget("bg"), foreground="black")
        self.style.configure('CommError.TCombobox') #, fieldbackground="red", foreground="white")
        self.style.configure('CommOK.TCombobox')#, fieldbackground="white", foreground="black")
        self.style.configure('CommError.TEntry') #, fieldbackground="red", foreground="white")
        self.style.configure('CommOK.TEntry')#, fieldbackground="white", foreground="black")

        frame1 = ttk.Frame(self)
        frame1.grid(row=0, column = 0, columnspan=4, sticky=tk.W+tk.E)

        # Default filenames
        today = datetime.datetime.now().strftime("%d-%m-%Y")
        self.saveFile = tk.StringVar()
        self.saveFile.set(os.getcwd() + '/' + "EmXX.All." + today + ".csv")
        sfLab = ttk.Label(frame1, text="All Data") 
        sfLab.grid(row=0, column = 0, sticky=tk.E, pady=5)
        saveFileEnt = ttk.Entry(frame1, textvariable=self.saveFile, width=80) 
        saveFileEnt.grid(row=0, column = 1, columnspan=2, sticky=tk.W, pady=5)

        self.savePlotFile = tk.StringVar()
        self.savePlotFile.set(os.getcwd() + '/' + "EmXX.Plot." + today + ".csv")
        spfLab = ttk.Label(frame1, text="Plot Data") 
        spfLab.grid(row=1, column = 0, sticky=tk.E, pady=5)
        savePlotFileEnt = ttk.Entry(frame1, textvariable=self.savePlotFile, width=80) 
        savePlotFileEnt.grid(row=1, column = 1, columnspan=2, sticky=tk.W, pady=5)

        operLab = ttk.Label(frame1, text="Operator") 
        operLab.grid(row=2, column = 0, sticky=tk.E, pady=5)
        self.operator = tk.StringVar()
        self.operator.set(config['Operator']['Name'])
        self.operEnt = ttk.Entry(frame1, textvariable = self.operator) 
        self.operEnt.grid(row=2, column = 1, sticky=tk.W, pady=5)

        # Lats & longs
        frame2 = ttk.LabelFrame(self, text="Global Positioning System")
        frame2.grid(row=1, column = 0, columnspan=2, sticky=tk.W+tk.E+tk.N)

        # GPS
        self.frame2b = ttk.Frame(frame2, style="CommOK.TFrame")
        self.frame2b.grid(row=1, column = 0, columnspan=5, pady=6, sticky=tk.W+tk.E)

        self.GPSModeLab = ttk.Label(self.frame2b, text="Mode", style="CommOK.TLabel") 
        self.GPSModeBx = ttk.Combobox(self.frame2b, values=['Undefined', 'IP', 'Bluetooth', 'Serial'], width=15, style="CommOK.TCombobox")
        self.GPSModeBx.set(config['GPS1']['Mode'])
        self.GPSModeBx.bind('<<ComboboxSelected>>', self.onSelectModeGPS)
        self.GPSModeDesc = ttk.Label(self.frame2b, text="", style="CommOK.TLabel") 
        self.GPSMsgLab = ttk.Label(self.frame2b, text="", style="CommOK.TLabel") 

        self.IPAddress = tk.StringVar()

        self.IPAddress.set(config['GPS1']['Address'].split(":")[0])
        self.IPAddress.trace_add("write", lambda name, index, mode, sv=self.IPAddress: self.IPHostCallback(self.IPAddress))

        self.IPPort = tk.StringVar()
        if (":" in config['GPS1']['Address']):
            self.IPPort.set(config['GPS1']['Address'].split(":")[1])
        else:
            self.IPPort.set("")
        self.IPPort.trace_add("write", lambda name, index, mode, sv=self.IPAddress: self.IPPortCallback(self.IPPort))
    
        self.GPSAddr = ttk.Entry(self.frame2b, textvariable=self.IPAddress, width=16) 
        self.GPSPort = ttk.Entry(self.frame2b, textvariable=self.IPPort, width=8) 
        self.GPSAddrLab = ttk.Label(self.frame2b, text="Address", style="CommOK.TLabel") 
        self.GPSPortLab = ttk.Label(self.frame2b, text="Port", style="CommOK.TLabel") 
        self.GPSLstBx = ttk.Combobox(self.frame2b, values=getAddresses( config['GPS1']['Mode'] ), 
                                         width=15, style="CommOK.TCombobox")
        self.GPSLstBx.bind('<<ComboboxSelected>>', self.onSelectAddressGPS)
        self.GPSDescLab = ttk.Label(self.frame2b, text="", style="CommOK.TLabel") 
        self.GPSLstLab = ttk.Label(self.frame2b, text="", style="CommOK.TLabel") 
        self.GPSLstBx = ttk.Combobox(self.frame2b, values=getAddresses( config['GPS1']['Mode'] ), width=15, style="CommOK.TCombobox")
        self.GPSDescLab = ttk.Label(self.frame2b, text="", style="CommOK.TLabel") 

        XLab = ttk.Label(frame2, text="Lng") 
        XLab.grid(row=2, column = 0, pady=5)
        self.X1Val = tk.DoubleVar()
        self.X1Val.set(0.0)
        XEnt = ttk.Entry(frame2, textvariable=self.X1Val) 
        XEnt.grid(row=2, column = 1, padx=5, pady=5)

        YLab = ttk.Label(frame2, text="Lat") 
        YLab.grid(row=3, column = 0, pady=5)
        self.Y1Val = tk.DoubleVar()
        self.Y1Val.set(0.0)
        YEnt = ttk.Entry(frame2, textvariable=self.Y1Val) 
        YEnt.grid(row=3, column = 1, padx=5, pady=5)

        self.H1Val = tk.DoubleVar()  # not displayed
        self.H1Val.set(0.0)
        self.GPSQualityVal = tk.IntVar()  # not displayed
        self.GPSQualityVal.set(0)

        self.doGPSUI(self.frame2b)

        # EM info
        frame3 = ttk.LabelFrame(self, text="EM")
        frame3.grid(row=2, column = 0, columnspan=2, sticky=tk.W+tk.E+tk.S)
        
        self.frame3a = ttk.Frame(frame3)
        self.frame3a.grid(row=0, column = 0, columnspan=8, sticky=tk.W+tk.E)
        self.EMModeLab = ttk.Label(self.frame3a, text="Mode", style="CommOK.TLabel") 
        self.EMModeLab.grid(row=0, column = 0, padx=5, pady=6)
        self.EMModeCbBx = ttk.Combobox(self.frame3a, values=["Undefined", "Bluetooth", "Serial"], width=15, style="CommOK.TCombobox")
        self.EMModeCbBx.set(config['EM']['Mode'])
        self.EMModeCbBx.bind('<<ComboboxSelected>>', self.onSelectModeEM)
        self.EMModeCbBx.grid(row=0, column = 1, padx=5, pady=6)

        self.EMLab = ttk.Label(self.frame3a, text="Port", style="CommOK.TLabel") 
        self.EMLab.grid(row=1, column = 0, padx=5, pady=6)
        self.EMCbBx = ttk.Combobox(self.frame3a, values=getAddresses(config['EM']['Mode']), width=15, style="CommOK.TCombobox")
        self.EMCbBx.set(config['EM']['Address'])
        config['EM']['Baud'] = '38400' #fixme

        self.EMCbBx.bind('<<ComboboxSelected>>', self.onSelectAddressEM)
        self.EMCbBx.grid(row=1, column = 1, padx=5, pady=6)
        self.EMDescLab = ttk.Label(self.frame3a, text="") 

        self.EMDescLab.grid(row=1, column = 2, padx=5, sticky=tk.W+tk.E, columnspan=6)

        frame3b = ttk.Frame(frame3)
        frame3b.grid(row=1, column = 0, columnspan=8, sticky=tk.W + tk.E)
        TempLab = ttk.Label(frame3b, text="Temperature", style="CommOK.TLabel") 
        TempLab.grid(row=0, column = 0, pady=6)
        self.EM_TemperatureVal= tk.DoubleVar()
        self.EMTemperature = ttk.Label(frame3b, textvariable=self.EM_TemperatureVal) 
        self.EMTemperature.grid(row=0, column = 1, padx=5, pady=6)


        self.D025Lab = ttk.Label(frame3, text="025", style="CommOK.TLabel") 
        self.D025Lab.grid(row=2, column = 0, pady=5)
        self.EM_PRPHVal = tk.DoubleVar()
        self.EM_PRPHIVal = tk.DoubleVar()
        D025Ent = ttk.Entry(frame3, textvariable=self.EM_PRPHVal, width=8) 
        D025Ent.grid(row=2, column = 1, pady=5)
        
        self.D05Lab = ttk.Label(frame3, text="05", style="CommOK.TLabel") 
        self.D05Lab.grid(row=2, column = 2, pady=5)
        self.EM_PRP1Val = tk.DoubleVar()
        self.EM_PRPI1Val = tk.DoubleVar()
        D05Ent = ttk.Entry(frame3, textvariable=self.EM_PRP1Val, width=8) 
        D05Ent.grid(row=2, column = 3, pady=5)

        self.D10Lab = ttk.Label(frame3, text="10", style="CommOK.TLabel") 
        self.D10Lab.grid(row=2, column = 4, pady=5)
        self.EM_PRP2Val = tk.DoubleVar()
        self.EM_PRPI2Val = tk.DoubleVar()
        D10Ent = ttk.Entry(frame3, textvariable=self.EM_PRP2Val, width=8) 
        D10Ent.grid(row=2, column = 5, pady=5)

        self.D075Lab = ttk.Label(frame3, text="075", style="CommOK.TLabel") 
        self.D075Lab.grid(row=3, column = 0, pady=5)
        self.EM_HCPHVal = tk.DoubleVar()
        self.EM_HCPIHVal = tk.DoubleVar()
        D075Ent = ttk.Entry(frame3, textvariable=self.EM_HCPHVal, width=8) 
        D075Ent.grid(row=3, column = 1, pady=5)
        
        self.D15Lab = ttk.Label(frame3, text="15", style="CommOK.TLabel") 
        self.D15Lab.grid(row=3, column = 2, pady=5)
        self.EM_HCP1Val = tk.DoubleVar()
        self.EM_HCPI1Val = tk.DoubleVar()
        D15Ent = ttk.Entry(frame3, textvariable=self.EM_HCP1Val, width=8) 
        D15Ent.grid(row=3, column = 3, pady=5)

        self.D30Lab = ttk.Label(frame3, text="30", style="CommOK.TLabel") 
        self.D30Lab.grid(row=3, column = 4, pady=5)
        self.EM_HCP2Val = tk.DoubleVar()
        self.EM_HCPI2Val = tk.DoubleVar()
        D30Ent = ttk.Entry(frame3, textvariable=self.EM_HCP2Val, width=8) 
        D30Ent.grid(row=3, column = 5, pady=5)

       # Undisplayed 
        self.TrackVal= tk.DoubleVar()
        self.SpeedVal= tk.DoubleVar()
        self.EM_VoltsVal= tk.DoubleVar()
        self.EM_PitchVal= tk.DoubleVar()
        self.EM_RollVal= tk.DoubleVar()


        frame4 = ttk.LabelFrame(self, text="Tracking")
        frame4.grid(row=1, column = 3, columnspan=2, rowspan=2, sticky=tk.W+tk.E+tk.N)
        self.track = tk.Canvas(frame4)
        self.track.grid(row=0, column = 0, sticky=tk.W+tk.E+tk.N)

        # The plot we are measuring
        large_font = ('Verdana',35)

        frame5 = ttk.LabelFrame(self, text="Sequence Number")
        frame5.grid(row=3, column = 0, columnspan=4, sticky=tk.W+tk.E)

        self.SeqVal = tk.StringVar()
        self.SeqVal.set("0")

        SeqEnt = ttk.Entry(frame5, textvariable=self.SeqVal, width=8,font=large_font) 
        SeqEnt.grid(row=0, column = 0, rowspan=2, pady=5, padx=10)

        # Fires a single line of data to the plot file
        SeqBtn = ttk.Button(frame5, text="Save & Advance", command=self.doSequence)
        SeqBtn.grid(row=0, column = 1, rowspan=2, pady=5, padx=10, sticky=tk.N+tk.S+tk.E+tk.W)

        self.SeqDirection = tk.IntVar()
        self.SeqDirection.set(1)
        SDButtonUp = ttk.Radiobutton(frame5, text="Decrement", variable=self.SeqDirection, value= -1)
        SDButtonUp.grid(row=0, column = 2, pady=5, padx=10, sticky=tk.W)
        SDButtonDown = ttk.Radiobutton(frame5, text="Increment", variable=self.SeqDirection, value= 1)
        SDButtonDown.grid(row=1, column = 2, pady=5, padx=10, sticky=tk.W)

        frame6 = ttk.Frame(self)
        frame6.grid(row=4, column = 0, columnspan=4, sticky=tk.W+tk.E)

        # When set, fires a regular reading to the continuous file
        self.running = None
        self.StartPauseBtn = ttk.Button(frame6, text="Start", command=self.startOrPause)
        self.StartPauseBtn.grid(row=0, column = 0, pady=5, padx=10)

        ExitBtn = ttk.Button(frame6, text="Exit", command=self.shutDown)
        ExitBtn.grid(row=0, column = 1, pady=5, padx=10)

        self.pack()
        self.clearTracks()

        self.monitor = root.after(250, self.doMonitor)

    def doGPSUI(self, w):

        for c in w.winfo_children():
            c.grid_forget()
        self.X1Val.set(0)
        self.Y1Val.set(0)
        self.GPSQualityVal.set(0)
        self.GPSModeLab.grid(row=0, column = 0, padx=5, pady=6)
        self.GPSModeBx.grid(row=0, column = 1, padx=5, pady=6)
        #self.GPSModeDesc.grid(row=0, column = 2, columnspan=6, pady=6)
        self.GPSMsgLab.grid(row=0, column = 2, columnspan=6, pady=6)

        if (config['GPS1']['Mode'] == "IP"):

            self.GPSAddrLab.grid(row=1, column = 0, padx=5, pady=6)
            self.GPSAddr.grid(row=1, column = 1, padx=5, pady=6)

            self.GPSPortLab.grid(row=1, column = 2, padx=5, pady=6)
            self.GPSPort.grid(row=1, column = 3, padx=5, pady=6)

        if (config['GPS1']['Mode'] == "Serial"):
            currentCOMPorts = getAddresses("Serial")
#fixme - if they change mode the address will be invalid            
#            if (config['GPS1']['Address'] not in currentCOMPorts):
#                config['GPS1']['Address'] = currentCOMPorts[0]

            self.GPSLstLab.configure(text="Port")
            self.GPSLstBx.set(config['GPS1']['Address'])
            self.GPSLstBx.configure(values = currentCOMPorts)
            desc = comPortDescriptions.get(config['GPS1']['Address'], 0)
            if desc:
                self.GPSDescLab.configure(text=desc) # Adjacent 
            else:
                self.GPSDescLab.configure(text="")
            self.GPSLstLab.grid(row=1, column = 0, padx=5, pady=6)
            self.GPSLstBx.grid(row=1, column = 1, padx=5, pady=6)
            self.GPSDescLab.grid(row=1, column = 2, padx=5, pady=6, sticky=tk.E+tk.W)

        if (config['GPS1']['Mode'] == "Bluetooth"):
            currentBTNames = getAddresses("Bluetooth")
#            if (config['GPS1']['Address'] not in currentBTNames):
#                config['GPS1']['Address'] = currentBTNames[0]

            self.GPSLstLab.configure(text="Device")
            self.GPSLstBx.set(config['GPS1']['Address'])
            self.GPSLstBx.configure(values = currentBTNames)
            self.GPSLstBx.bind('<<ComboboxSelected>>', self.onSelectAddressGPS)
            self.GPSLstLab.grid(row=1, column = 0, padx=5, pady=6)
            self.GPSLstBx.grid(row=1, column = 1, padx=5, pady=6)
            self.GPSDescLab.grid(row=1, column = 2, padx=5, pady=6, sticky=tk.E+tk.W)

            #desc = BTPortDescriptions.get(config['GPS1']['Address'], 0)
            #if desc:
            #    self.GPSDescLab.configure(text=desc) # Adjacent 
            #else:
            #    self.GPSDescLab.configure(text="")
            #self.GPSLstBx.configure(values = getAddresses( value ))

    def onSelectModeGPS(self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except: 
            pass

        config['GPS1']['Mode'] = value
        self.onGPSNoError()
        self.doGPSUI(self.frame2b)
        self.restartGPS1Flag.set()
        return
    
    
    def onSelectAddressGPS (self, evt):
        w = evt.widget
        value = w.get()
        config['GPS1']['Address'] = value
        self.onGPSNoError()
        desc = comPortDescriptions.get(value, 0)
        if desc:
            self.GPSDescLab.configure(text=desc, style="CommOK.TLabel")
        else:
            self.GPSDescLab.configure(text="", style="CommOK.TLabel")
        self.GPSQualityVal.set(0)
        self.X1Val.set(0.0)
        self.Y1Val.set(0.0)
        
        self.restartGPS1Flag.set()
        self.lastGPS1Time = datetime.datetime.now() 
        saveConfig()

    def onGPSError (self, msg):
        self.ringTheBell()
        self.frame2b.configure(style="CommError.TFrame")
        self.GPSMsgLab.configure(text=msg)
        self.GPSModeLab.configure(style="CommError.TLabel")
        self.GPSMsgLab.configure(style="CommError.TLabel")
        self.GPSAddrLab.configure(style="CommError.TLabel")
        self.GPSPortLab.configure(style="CommError.TLabel")
        self.GPSDescLab.configure(style="CommError.TLabel")
        self.GPSLstLab.configure(style="CommError.TLabel")

    def onGPSNoError (self):
        s = self.frame2b.cget("style")
        if (s != "CommOK.TFrame" ):
            self.frame2b.configure(style="CommOK.TFrame")
            self.GPSMsgLab.configure(text="")
            self.GPSModeLab.configure(style="CommOK.TLabel")
            self.GPSMsgLab.configure(style="CommOK.TLabel")
            self.GPSAddrLab.configure(style="CommOK.TLabel")
            self.GPSPortLab.configure(style="CommOK.TLabel")
            self.GPSDescLab.configure(style="CommOK.TLabel")
            self.GPSLstLab.configure(style="CommOK.TLabel")

    def hasGPSError (self):
        s = self.frame2b.cget("style")
        if (s != "CommOK.TFrame" ):
            return True
        return False
    
    def onSelectModeEM (self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except:
            pass
        config['EM']['Mode'] = value
        if (value == "Serial"):
            currentCOMPorts = getAddresses("Serial")
            self.EMCbBx.configure(values = currentCOMPorts)
            if (config['EM']['Address'] not in currentCOMPorts):
                config['EM']['Address'] = currentCOMPorts[0]
            desc = comPortDescriptions.get(config['EM']['Address'], 0)
            if desc:
                self.EMDescLab.configure(text=desc) 
            else:
                self.EMDescLab.configure(text="")
        if (value == "Bluetooth"):
            currentBTNames = getAddresses("Bluetooth")
            self.EMCbBx.configure(values = currentBTNames)
            if (config['EM']['Address'] not in currentBTNames):
                config['EM']['Address'] = currentBTNames[0]
            desc = BTPortDescriptions.get(config['EM']['Address'], 0)
            if desc:
                self.EMDescLab.configure(text=desc) 
            else:
                self.EMDescLab.configure(text="")

        self.restartEMFlag.set()
        self.onEMNoError()
        #print("onSelectModeEM: mode=" + value)

    def onSelectAddressEM (self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except:
            pass
        config['EM']['Address'] = value
        self.onEMNoError ()

        desc = ""
        if (config['EM']['Mode'] == "Serial"):
            desc = comPortDescriptions.get(value, 0)
        if (config['EM']['Mode'] == "Bluetooth"):
            desc = BTPortDescriptions.get(value, 0)
            
        if desc:
            self.EMDescLab.configure(text=desc, style="CommOK.TLabel")
        else:
            self.EMDescLab.configure(text="", style="CommOK.TLabel")

        self.restartEMFlag.set()
        self.lastEMTime = datetime.datetime.now() 
        saveConfig()
        #print("onSelectAddressEM: addr=" + value)

    # Ensure we dont get too many bells
    def ringTheBell (self):
        if (datetime.datetime.now() - self.lastBellTime).total_seconds() > 5:
            root.bell()
            self.lastBellTime = datetime.datetime.now()

    def onEMError (self, msg):
        self.ringTheBell()
        self.frame3a.configure(style="CommError.TFrame")
        self.EMLab.configure(style="CommError.TLabel")
        self.EMModeLab.configure(style="CommError.TLabel")
        self.EMCbBx.configure(style="CommError.TCombobox")
        self.EMDescLab.configure(text=msg, style="CommError.TLabel")

    def onEMNoError (self):
        s = self.frame3a.cget("style")
        if (s != "CommOK.TFrame" ):
            self.frame3a.configure(style="CommOK.TFrame")
            self.EMLab.configure(style="CommOK.TLabel")
            self.EMModeLab.configure(style="CommOK.TLabel")
            self.EMCbBx.configure(style="CommOK.TCombobox")
            self.EMDescLab.configure(text="", style="CommOK.TLabel")

    def hasEMError (self):
        s = self.frame3a.cget("style")
        if (s != "CommOK.TFrame" ):
            return True
        return False

    # Write a line to the plot file, and advance to the next reading
    def doSequence (self):
        self.doitPlot()
        current = self.SeqVal.get()
        seqNum = int(current) + self.SeqDirection.get()
        self.SeqVal.set(str(seqNum))
            
        global root
        root.bell()

    # toggle continuous operation on/off
    def startOrPause(self):
        #print("r=" + str(self.running != None))
        if (self.running == None):
            self.StartPauseBtn.config(text = "Pause")
            self.startLogging()
        else:
            self.StartPauseBtn.config(text = "Start")
            self.pauseLogging()

    def startLogging(self):
        if not os.path.exists(self.saveFile.get()):
            with open(self.saveFile.get(), 'w') as the_file:
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Longitude,Latitude,Elevation,Speed,Track,Quality,EM PRP1,EM PRP2,EM PRPH,EM HCP1,EM HCP2,EM HCPH,EM PRPI1,EM PRPI2,EM PRPIH,EM HCPI1,EM HCPI2,EM HPCIH,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=' + str(self.operator.get()) + '\n')
        self.doLogging()

    def pauseLogging(self):
        if (self.running != None):
            root.after_cancel(self.running)
            self.running = None

    def doMonitor(self):
        try:
            if not self.hasGPSError() and (datetime.datetime.now() - self.lastGPS1Time).total_seconds() > 2:
                self.onGPSError("Timeout")

            #if (self.GPSQualityCode() != "Invalid" and self.GPSQualityCode() != "RTK Fixed"): # invalid will trigger a timeout
            #    self.onGPSError("Quality: " + self.GPSQualityCode())

            if (self.hasGPSError()):
                self.numGPSErrors += 1

            if (self.numGPSErrors > 10):
                self.onGPSNoError()
                self.numGPSErrors = 0

            if (datetime.datetime.now() - self.lastEMTime).total_seconds() > 2:
                if (not self.hasEMError()):
                    self.onEMError("Timeout")
                    self.restartEMFlag.set()

            if (self.hasEMError()):
                self.numEMErrors += 1

            if (self.numEMErrors > 10):
                self.onEMNoError()
                self.numEMErrors = 0

            # Check for new devices being plugged in
            if (hasattr(self, "GPSLstBx") | hasattr(self, "EMModeCbBx")):
                checkBTPorts()
                checkComPorts()

            # Ensure new devices are added to the combobox
            if (hasattr(self, "GPSLstBx")):
                if config['GPS1']['Mode'] != "Undefined":
                    oldAddresses = self.GPSLstBx.cget('values')
                    newAddresses = getAddresses(config['GPS1']['Mode'])
                    if (oldAddresses != newAddresses):
                        self.GPSLstBx.config(values=newAddresses)
                else:
                    self.GPSLstBx.set("")
                    self.GPSLstBx.configure(values=[])

            if hasattr(self, "EMCbBx"):
                if config['EM']['Mode'] != "Undefined":
                    oldAddresses = self.EMCbBx.cget('values')
                    newAddresses = getAddresses(config['EM']['Mode'])
                    if (oldAddresses != newAddresses):
                        self.EMCbBx.config(values=newAddresses)
                else:
                    self.EMCbBx.set("")
                    self.EMCbBx.configure(values = [])

        except Exception as e:
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
            pass

        self.monitor = root.after(250, self.doMonitor)

    def doLogging(self):
        self.doit()
        self.running = root.after(500, self.doLogging)

    def shutDown(self):
        self.stopFlag.set()
        global root
        root.destroy()
        sys.exit(0)

    def getE1(self):
        return("," + str(self.EM_PRP1Val.get()) + "," + str(self.EM_PRP2Val.get()) + "," + str(self.EM_PRPHVal.get())+ \
                "," + str(self.EM_HCP1Val.get()) + "," + str(self.EM_HCP2Val.get()) + "," + str(self.EM_HCPHVal.get()) + \
                "," + str(self.EM_PRPI1Val.get()) + "," + str(self.EM_PRPI2Val.get()) + "," + str(self.EM_PRPHIVal.get()) + \
                "," + str(self.EM_HCPI1Val.get()) + "," + str(self.EM_HCPI2Val.get()) + "," + str(self.EM_HCPIHVal.get()) + \
                "," + str(self.EM_VoltsVal.get()) + "," + str(self.EM_TemperatureVal.get()) + \
                "," + str(self.EM_PitchVal.get()) + "," + str(self.EM_RollVal.get()))

    # Write to the continuous output file 
    def doit(self):
        time_now = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S.%f')
        line = time_now +  "," + \
            str(self.X1Val.get()) + "," + str(self.Y1Val.get()) + "," + str(self.H1Val.get()) + "," + \
            str(self.SpeedVal.get()) + "," + str(self.TrackVal.get()) + "," + self.GPSQualityCode() +\
                self.getE1() + \
                '\n'
        with open(self.saveFile.get(), 'a') as the_file:
            the_file.write(line)
            the_file.flush()
        self.markTrack(self.X1Val.get(), self.Y1Val.get())

    def markTrack(self, X, Y):
        self.recalcTrackExtents() 
        cx, cy = self.wToC(X, Y)
        if cx is not None:
            self.track.create_oval(cx-5, cy-5, cx+5, cy+5, fill="red", outline = "")
        self.coords.append([X, Y])

    # Latitude/longitude coord to a pixel coordinate 
    def wToC(self, X, Y):
        if (len(self.coords) < 2 or 
            self.trackWidth <= 0 or 
            self.trackHeight <= 0 or
            self.geoWidth <= 0 or 
            self.geoHeight <= 0): 
            return None, None

        deltaLat = Y - self.trackMinLat
        deltaLong= X - self.trackMinLong

        latRatio = deltaLat / self.geoWidth
        longRatio= deltaLong / self.geoHeight

        x = max(0, min(self.trackWidth, latRatio * self.trackWidth))
        y = max(0, min(self.trackHeight, longRatio * self.trackHeight))

        return x,y

    def recalcTrackExtents(self):
        if (len(self.coords) < 2 or
            (datetime.datetime.now() - self.coordStamp).total_seconds() < 30):
            return

        self.trackMinLong = self.trackMinLat = 1000
        self.trackMaxLong = self.trackMaxLat = -1000
        for coord in self.coords:
            if coord[0] < self.trackMinLong:
                self.trackMinLong = coord[0]
            if coord[0] > self.trackMaxLong:
                self.trackMaxLong = coord[0]
            if coord[1] < self.trackMinLat:
                self.trackMinLat = coord[1]
            if coord[1] > self.trackMaxLat:
                self.trackMaxLat = coord[1]

        self.trackWidth = int(self.track.cget("width"))
        self.trackHeight = int(self.track.cget("height"))
        self.geoWidth = self.trackMaxLat - self.trackMinLat
        self.geoHeight= self.trackMaxLong - self.trackMinLong

        self.track.delete("all")
        for long,lat in self.coords:
            cx, cy = self.wToC(long, lat)
            if cx is not None:
                self.track.create_oval(cx-5,cy-5,cx + 5, cy+5, fill="red", outline = "")

        self.coordStamp = datetime.datetime.now()
                           
    def clearTracks(self):
        print("Cleared tracks")
        self.coordStamp = datetime.datetime.now()
        self.coords = []
        self.trackMinLong = self.trackMinLat = 1000
        self.trackMaxLong = self.trackMaxLat = -1000
        self.geoWidth = self.geoHeight = 0
        self.trackWidth = self.trackHeight = 0

    # Write to the plot file 
    def doitPlot(self):
        if not os.path.exists(self.savePlotFile.get()):
            with open(self.savePlotFile.get(), 'w') as the_file:
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Plot,Longitude 1,Latitude 1,Height 1,E1_PRP1,E1_PRP2,E1_PRPH,E1_HCP1,E1_HCP2,E1_HCPH,E1_PRPI1,E1_PRPI2,E1_PRPIH,E1_HCPI1,E1_HCPI2,E1_HCPIH,E1_Volts,E1_Temperature,E1_Pitch,E1_Roll,Operator=' + str(self.operator.get()) + '\n')
        time_now = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S.%f')
        line = time_now + "," + self.SeqVal.get() + "," +\
            str(self.X1Val.get()) + "," + str(self.Y1Val.get()) + "," + str(self.H1Val.get()) + "," + \
            self.getE1() + \
            '\n'

        with open(self.savePlotFile.get(), 'a') as the_file:
            the_file.write(line)
            the_file.flush()

        self.markTrack(self.X1Val.get(), self.Y1Val.get())

    def GPSQualityCode(self):
        code = self.GPSQualityVal.get()
        if (code == 0): 
            return "Invalid"
        if (code == 1): 
            return "GPS"
        if (code == 2): 
            return "Diff. GPS"
        if (code == 3): 
            return "NA"
        if (code == 4): 
            return "RTK Fixed"
        if (code == 5): 
            return "RTK Float"
        if (code == 6): 
            return "INS DeadR"
        return "Unknown"

    def openComms(self, cfg):
        print("Opening " + cfg['Mode'] + ' ' + cfg['Address'] + '\n')
        s = self.openCommsReal(cfg)
        #try: 
        #    s.write(b'%\r\n') # Sometimes this is needed, sometimes not...
        #except:
        #    pass
        #finally:
        #    s.close()
        #sleep(1) ??
        #s = self.openCommsReal(cfg)
        return s

    def openCommsReal(self, cfg):
        if (cfg['Mode'] == "Bluetooth"):
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            btName = cfg['Address']
            btAddr = ""
            for addr, name in BTPortDescriptions.items(): 
                if name == btName:
                    btAddr = addr
            s.connect((btAddr, 1))
        elif (cfg['Mode'] == "IP"):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((cfg['Address'], int(cfg['Port'])))
        elif (cfg['Mode'] == "Serial"):
            s = serial.Serial(cfg['Address'], cfg['Baud'], timeout=2, write_timeout=2)
        else:
            raise Exception("Unknown mode " + cfg['Mode'])
        return s

    # The gps reader thread
    def gps1_read(self, cfgName):
        while not self.stopFlag.is_set():
            cfg = config[cfgName]
            if (cfg['Mode'] == "Undefined") | ("No devices" in cfg['Address']):
               self.lastGPS1Time = datetime.datetime.now()
            else:
                s = None
                try:
                    self.restartGPS1Flag.clear()
                    self.X1Val.set(0.0)
                    self.Y1Val.set(0.0)
                    self.H1Val.set(0.0)
                    s = self.openComms(cfg)

                    while (not self.stopFlag.is_set() ) & (not self.restartGPS1Flag.is_set()):
                        line = self.buffered_readLine(s) 
                        # nonblocking read()? - https://stackoverflow.com/questions/38757906/python-3-non-blocking-read-with-pyserial-cannot-get-pyserials-in-waiting-pro/
                        #print("line = " + line)
                        linedata = str(line)[1:]
                        splitlines = linedata.split(',')
    
                        if ("GPGGA" in splitlines[0]) or ("GNGGA" in splitlines[0]):
                            S = decimal_degrees(*dm(float(splitlines[2])))
                            if splitlines[3].find('S') >= 0:
                                S = S * -1
                            E = decimal_degrees(*dm(float(splitlines[4])))
                            H = float(splitlines[9])
                            Q = int(splitlines[6])
                            with lock:
                                self.X1Val.set(E)
                                self.Y1Val.set(S)
                                self.H1Val.set(H)
                                self.GPSQualityVal.set(Q)
                                #print("X= " + str(self.XVal.get()))
                            self.lastGPS1Time = datetime.datetime.now()
                        if "GPVTG" in splitlines[0]: # http://aprs.gids.nl/nmea/#vtg
                            T = 0.0
                            if splitlines[1] != "":
                                T = float(splitlines[1])
                            S = 0.0
                            if splitlines[7] != "":
                                S = float(splitlines[7])
                            with lock:
                                self.TrackVal.set(T)
                                self.SpeedVal.set(S)
                            #print("Track= " + str(T))

                except Exception as e:
                    if hasattr(e, 'message'):
                        self.onGPSError("Exception opening " + cfg['Address'] + e.message)
                    else:
                        self.onGPSError("Exception opening " + cfg['Address'])
                        print(e)
                    pass
                if s is not None:
                    s.close()
            time.sleep(1)

    def buffered_readLine(self, socket):
        encoding = 'utf-8'
        line = ""
        while True:
            part = socket.recv(1)
            if part != b'\n':
                line+=str(part, encoding)
            elif part == b'\n':
                break
        return line

    # The em reader thread
    def em1_read(self, cfgName):
        while not self.stopFlag.is_set():
            cfg = config[cfgName]
            if (cfg['Mode'] == "Undefined") | ("No devices" in cfg['Address']):
               self.lastEMTime = datetime.datetime.now()
            else:
                self.restartEMFlag.clear()
                self.EM_HCP1Val.set(0.0)
                self.EM_HCPI1Val.set(0.0)
                self.EM_PRP1Val.set(0.0)
                self.EM_PRPI1Val.set(0.0)
                self.EM_HCP2Val.set(0.0)
                self.EM_HCPI2Val.set(0.0)
                self.EM_PRP2Val.set(0.0)
                self.EM_PRPI2Val.set(0.0)
                self.EM_HCPHVal.set(0.0)
                self.EM_HCPIHVal.set(0.0)
                self.EM_PRPHVal.set(0.0)
                self.EM_PRPHIVal.set(0.0)
                s = None
                try:
                    self.onEMNoError()
                    s = self.openComms(cfg)

                    line = ''
                    while (not self.stopFlag.is_set() ) & (not self.restartEMFlag.is_set() ):
                        while (line.find('\n') < 0 & (not self.restartEMFlag.is_set())):
                            if (s.in_waiting > 0):
                                line = line + s.read(s.in_waiting).decode('ascii') 
                            if (s.in_waiting <= 0):
                                time.sleep(0.01) 
                        linedata = line[:line.find('\n')]
                        line = line[line.find('\n')+1:]
                        splitlines = linedata.split(',')
                        if ("PDLM1" in linedata) and (len(splitlines) >= 5):
                            with lock:
                                self.EM_HCP1Val.set(splitlines[2])   #HCP conductivity in mS/m
                                self.EM_HCPI1Val.set(splitlines[3])  #HCP inphase in ppt
                                self.EM_PRP1Val.set(splitlines[4])   #PRP conductivity in mS/m
                                self.EM_PRPI1Val.set(splitlines[5].split('*')[0]) #PRP inphase in ppt
                            self.lastEMTime = datetime.datetime.now()
                        elif ("PDLM2" in linedata) & (len(splitlines) >= 5):
                            with lock:
                                self.EM_HCP2Val.set(splitlines[2])      #HCP conductivity in mS/m
                                self.EM_HCPI2Val.set(splitlines[3])     #HCP inphase in ppt
                                self.EM_PRP2Val.set(splitlines[4])      #PRP conductivity in mS/m
                                self.EM_PRPI2Val.set(splitlines[5].split('*')[0])      #PRP inphase in ppt
                            self.lastEMTime = datetime.datetime.now()
                        elif ("PDLMH" in linedata) & (len(splitlines) >= 5):
                            with lock:
                                self.EM_HCPHVal.set(splitlines[2])      #HCP conductivity in mS/m
                                self.EM_HCPIHVal.set(splitlines[3])     #HCP inphase in ppt
                                self.EM_PRPHVal.set(splitlines[4])      #PRP conductivity in mS/m
                                self.EM_PRPHIVal.set(splitlines[5].split('*')[0])      #PRP inphase in ppt
                            self.lastEMTime = datetime.datetime.now()
                        elif ("PDLMA" in linedata) & (len(splitlines) >= 4):
                            #print('pdlma: ' + linedata)
                            with lock:
                                self.EM_VoltsVal.set(float(splitlines[1]))
                                self.EM_TemperatureVal.set(float(splitlines[2]))
                                self.EM_PitchVal.set(float(splitlines[3]))
                                self.EM_RollVal.set(float(splitlines[4].split('*')[0]))
                            self.lastEMTime = datetime.datetime.now()

                        ROLL = self.EM_RollVal.get()
                        if float(abs(ROLL)) > 20:
                            self.onEMError(' Roll angle: ' + str(ROLL))

                        #print("stop= " + str(self.stopFlag.is_set()) + "," + "restart= " + str( self.restartEMFlag.is_set()))
                    # end while    
                except Exception as e:
                    self.onEMError("Exception opening " + cfg['Address'] )
                    if hasattr(e, 'message'):
                        print('msg=' + e.message)
                    else:
                        print(e)
                    pass
                if (s is not None):
                    s.close()
            time.sleep(1)

app = None
root = None
def main():
    global root
    root = tk.Tk()
    root.geometry("600x625+100+100")
    app = EMApp()
    root.protocol("WM_DELETE_WINDOW", app.shutDown)

    root.mainloop()

if __name__ == '__main__':
    main()
