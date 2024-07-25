from collections import defaultdict
import serial
import socket
from serial.tools import list_ports
import os
import platform
import sys
import subprocess
import time
import threading
import datetime
import getpass
import configparser

import numpy as np
import tkinter as tk
from tkinter import ttk

#from tendo import singleton
# 
#me = singleton.SingleInstance()

config = configparser.ConfigParser()
if not os.path.exists('Dualem_and_GPS_datalogger.ini'):
    config['GPS1'] = {'Mode': 'IP', 'Address': '10.0.0.1:5017', 'Baud' : 4800}
    #config['GPS1'] = {'Mode': 'Bluetooth', 'Address' : 'Facet Rover-9A22', 'Baud' : 4800}
    config['EM'] = {'Mode': 'Serial', 'Address' : 'COM4', 'Baud' : 38400}
    #config['EM'] = {'Mode': 'Undefined', 'Port': 'Undefined', 'Baud': 38400} # COM4
    config['Operator'] = {'Name' : getpass.getuser()}
    config['IP'] = {'Recent' : "10.0.0.1:5017" }
    config['Serial'] = {'Recent' : "COM1,COM4" }
    config['Bluetooth'] = {'Recent' : "Facet Rover-9A22" }
else:
    config.read('Dualem_and_GPS_datalogger.ini')

    if not config.has_option('GPS1', 'Baud'):
        config['GPS1']['Baud'] = "38400"

    if not config.has_option('EM', 'Baud'):
        config['EM']['Baud'] = "38400"

lock = threading.Lock()

def dm(x):
    degrees = int(x) // 100
    minutes = x - 100*degrees
    return degrees, minutes

def decimal_degrees(degrees, minutes):
    return degrees + minutes/60 

################## Initialisation here ##################

class EMApp(ttk.Frame):
    def __init__(self):
        super().__init__()
        self.comPortDescriptions = dict()
        self.BTPortDescriptions = dict()

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

        self.DiscoveryThread = threading.Thread(target=self.portDiscovery, args=('Discovery',), daemon = True)
        self.DiscoveryThread.start()
        self.workers.append(self.DiscoveryThread)

        self.numGPSErrors = 0
        self.numEMErrors = 0
        self.lastBellTime = datetime.datetime.now() #- datetime.timedelta(seconds=10)
    
    def IPHostCallback (self, variable):
        config['GPS1']["Address"] = variable.get()

    # Build the UI
    def initUI(self):
        global config
        self.master.title("EM")

        self.style = ttk.Style()

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
        self.frame2b = ttk.Frame(frame2)
        self.frame2b.grid(row=1, column = 0, columnspan=5, pady=6, sticky=tk.W+tk.E)

        self.GPSModeLab = ttk.Label(self.frame2b, text="Mode") 
        self.GPSModeBx = ttk.Combobox(self.frame2b, values=['Undefined', 'IP', 'Bluetooth', 'Serial'], width=15)
        self.GPSModeBx.set(config['GPS1']['Mode'])
        self.GPSModeBx.bind('<<ComboboxSelected>>', self.onSelectModeGPS)
        self.GPSModeDesc = ttk.Label(self.frame2b, text="") 
        self.GPSMsgLab = ttk.Label(self.frame2b, text="") 

        self.GPSBaudLab = ttk.Label(self.frame2b, text="Baud") 
        self.GPSBaudCbx = ttk.Combobox(self.frame2b, width=6, values=[50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200]) 
        self.GPSBaudCbx.set(config['GPS1']['Baud'])
        self.GPSBaudCbx.bind('<<ComboboxSelected>>', self.onSelectBaudGPS)

        self.IPAddress = tk.StringVar()

        self.IPAddress.set(config['GPS1']['Address'])
        self.IPAddress.trace_add("write", lambda name, index, mode, sv=self.IPAddress: self.IPHostCallback(self.IPAddress))
    
        self.GPSAddr = ttk.Entry(self.frame2b, textvariable=self.IPAddress, width=16) 
        self.GPSAddrLab = ttk.Label(self.frame2b, text="Address") 
        self.GPSLstBx = ttk.Combobox(self.frame2b, values=self.getAddresses( config['GPS1']['Mode'] ), width=15)
        self.GPSLstBx.bind('<<ComboboxSelected>>', self.onSelectAddressGPS)
        self.GPSDescLab = ttk.Label(self.frame2b, text="") 
        self.GPSLstLab = ttk.Label(self.frame2b, text="") 
        self.GPSLstBx = ttk.Combobox(self.frame2b, values=self.getAddresses( config['GPS1']['Mode'] ), width=15)
        self.GPSDescLab = ttk.Label(self.frame2b, text="") 

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
        self.frame3 = ttk.LabelFrame(self, text="Dual EM")
        self.frame3.grid(row=2, column = 0, columnspan=2, sticky=tk.W+tk.E+tk.S)
        
        self.frame3a = ttk.Frame(self.frame3)
        self.frame3a.grid(row=0, column = 0, columnspan=8, sticky=tk.W+tk.E)
        self.EMModeLab = ttk.Label(self.frame3a, text="Mode") 
        self.EMModeCbBx = ttk.Combobox(self.frame3a, values=["Undefined", "Bluetooth", "Serial"], width=15)
        self.EMModeCbBx.set(config['EM']['Mode'])
        self.EMModeCbBx.bind('<<ComboboxSelected>>', self.onSelectModeEM)

        self.EMBaudLab = ttk.Label(self.frame3a, text="Baud") 
        self.EMBaudCbx = ttk.Combobox(self.frame3a, width=6, values=[50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200]) 
        self.EMBaudCbx.set(config['EM']['Baud'])
        self.EMBaudCbx.bind('<<ComboboxSelected>>', self.onSelectBaudEM)

        self.EMLab = ttk.Label(self.frame3a, text="Port") 
        self.EMCbBx = ttk.Combobox(self.frame3a, width=15)

        self.EMCbBx.set(config['EM']['Address'])

        self.EMCbBx.bind('<<ComboboxSelected>>', self.onSelectAddressEM)
        self.EMDescLab = ttk.Label(self.frame3a, text="") 

        self.doEMUI(self.frame3a)

        frame3b = ttk.Frame(self.frame3)
        frame3b.grid(row=1, column = 0, columnspan=8, sticky=tk.W + tk.E)
        TempLab = ttk.Label(frame3b, text="Temperature") 
        TempLab.grid(row=0, column = 0, pady=6)
        self.EM_TemperatureVal= tk.DoubleVar()
        self.EMTemperature = ttk.Label(frame3b, textvariable=self.EM_TemperatureVal) 
        self.EMTemperature.grid(row=0, column = 1, padx=5, pady=6)

        self.D025Lab = ttk.Label(self.frame3, text="025") 
        self.D025Lab.grid(row=2, column = 0, pady=5)
        self.EM_PRPHVal = tk.DoubleVar()
        self.EM_PRPHIVal = tk.DoubleVar()
        D025Ent = ttk.Entry(self.frame3, textvariable=self.EM_PRPHVal, width=8) 
        D025Ent.grid(row=2, column = 1, pady=5)
        
        self.D05Lab = ttk.Label(self.frame3, text="05") 
        self.D05Lab.grid(row=2, column = 2, pady=5)
        self.EM_PRP1Val = tk.DoubleVar()
        self.EM_PRPI1Val = tk.DoubleVar()
        D05Ent = ttk.Entry(self.frame3, textvariable=self.EM_PRP1Val, width=8) 
        D05Ent.grid(row=2, column = 3, pady=5)

        self.D10Lab = ttk.Label(self.frame3, text="10") 
        self.D10Lab.grid(row=2, column = 4, pady=5)
        self.EM_PRP2Val = tk.DoubleVar()
        self.EM_PRPI2Val = tk.DoubleVar()
        D10Ent = ttk.Entry(self.frame3, textvariable=self.EM_PRP2Val, width=8) 
        D10Ent.grid(row=2, column = 5, pady=5)

        self.D075Lab = ttk.Label(self.frame3, text="075") 
        self.D075Lab.grid(row=3, column = 0, pady=5)
        self.EM_HCPHVal = tk.DoubleVar()
        self.EM_HCPIHVal = tk.DoubleVar()
        D075Ent = ttk.Entry(self.frame3, textvariable=self.EM_HCPHVal, width=8) 
        D075Ent.grid(row=3, column = 1, pady=5)
        
        self.D15Lab = ttk.Label(self.frame3, text="15") 
        self.D15Lab.grid(row=3, column = 2, pady=5)
        self.EM_HCP1Val = tk.DoubleVar()
        self.EM_HCPI1Val = tk.DoubleVar()
        D15Ent = ttk.Entry(self.frame3, textvariable=self.EM_HCP1Val, width=8) 
        D15Ent.grid(row=3, column = 3, pady=5)

        self.D30Lab = ttk.Label(self.frame3, text="30") 
        self.D30Lab.grid(row=3, column = 4, pady=5)
        self.EM_HCP2Val = tk.DoubleVar()
        self.EM_HCPI2Val = tk.DoubleVar()
        D30Ent = ttk.Entry(self.frame3, textvariable=self.EM_HCP2Val, width=8) 
        D30Ent.grid(row=3, column = 5, pady=5)

       # Undisplayed 
        self.TrackVal= tk.DoubleVar()
        self.SpeedVal= tk.DoubleVar()
        self.EM_VoltsVal= tk.DoubleVar()
        self.EM_PitchVal= tk.DoubleVar()
        self.EM_RollVal= tk.DoubleVar()


        self.frame4 = ttk.LabelFrame(self, text="Tracking")
        self.frame4.grid(row=1, column = 2, columnspan=2, rowspan=2, padx=2, sticky=tk.W+tk.E+tk.N+tk.S)
        self.canvas = tk.Canvas(self.frame4)
        self.canvas.grid(row=0, column = 0, sticky=tk.W+tk.E+tk.N+tk.S)
        self.chartButtonFrame = ttk.Frame(self.frame4)
        self.chartButtonFrame.grid(row=1, column = 0,sticky=tk.W)
        self.chartBtnTrack = ttk.Button(self.chartButtonFrame, text="Track", command = self.onTrackBtnPressed)
        self.chartBtnHist = ttk.Button(self.chartButtonFrame, text="Histogram", command = self.onHistBtnPressed)
        self.chartCombo = ttk.Combobox(self.chartButtonFrame, width=6,
                                       values=['PRPH', 'PRP1', 'PRP2', 'HCPH', 'HCP1', 'HCP2'])
        self.chartCombo.bind('<<ComboboxSelected>>', self.onSelectChartHist)
        self.chartCombo.set('PRPH')
        self.chartBtnTrack.grid(row=0, column = 0, padx=5, pady=5)
        self.chartBtnHist.grid(row=0, column = 1, padx=5, pady=5)
        self.chartCombo.grid(row=0, column = 2, padx=5, pady=5)

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

        self.errMsg = ttk.Label(self, text="", font = ('Verdana',20) )
        self.errMsgText = ""
        self.errMsgSource = []
        self.lastErrorTime = datetime.datetime.now() - datetime.timedelta(seconds=30)

        self.pack()
        self.clearTracks()
        self.clearEMRec()
        self.onTrackBtnPressed()
        self.chartMode = "Track"

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

        if (config['GPS1']['Mode'] == "Serial"):
            currentCOMPorts = self.getAddresses("Serial")
#fixme - if they change mode the address will be invalid            
#            if (config['GPS1']['Address'] not in currentCOMPorts):
#                config['GPS1']['Address'] = currentCOMPorts[0]

            self.GPSLstLab.configure(text="Port")
            self.GPSLstBx.set(config['GPS1']['Address'])
            self.GPSLstBx.configure(values = currentCOMPorts)
            desc = self.comPortDescriptions.get(config['GPS1']['Address'], 0)
            if desc:
                self.GPSDescLab.configure(text=desc) # Adjacent 
            else:
                self.GPSDescLab.configure(text="")
            self.GPSLstLab.grid(row=1, column = 0, padx=5, pady=6)
            self.GPSLstBx.grid(row=1, column = 1, padx=5, pady=6)
            self.GPSDescLab.grid(row=1, column = 2, padx=5, pady=6, sticky=tk.E+tk.W)

            self.GPSBaudLab.grid(row=0, column = 2, padx=5, pady=6)
            self.GPSBaudCbx.grid(row=0, column = 3, padx=5, pady=6)
            self.GPSBaudCbx.set(config['GPS1']['Baud'])

        if (config['GPS1']['Mode'] == "Bluetooth"):
            currentBTNames = self.getAddresses("Bluetooth")
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

    def doEMUI(self, w):
        for c in w.winfo_children():
            c.grid_forget()

        self.EMModeLab.grid(row=0, column = 0, padx=5, pady=6)
        self.EMModeCbBx.grid(row=0, column = 1, padx=5, pady=6)
        if (config['EM']['Mode'] == "Serial"):
            self.EMBaudLab.grid(row=0, column = 2, padx=5, pady=6)
            self.EMBaudCbx.grid(row=0, column = 3, padx=5, pady=6)
            self.EMBaudCbx.set(config['EM']['Baud'])

        self.EMLab.grid(row=1, column = 0, padx=5, pady=6)
        self.EMCbBx.grid(row=1, column = 1, padx=5, pady=6)
        self.EMDescLab.grid(row=1, column = 2, padx=5, sticky=tk.W+tk.E, columnspan=6)

    def onSelectModeGPS(self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except: 
            pass

        with lock:
            config['GPS1']['Mode'] = value
        while "GPS" in self.errMsgSource: self.errMsgSource.remove("GPS")
        self.doGPSUI(self.frame2b)
        self.restartGPS1Flag.set()
        self.saveConfig()
        self.clearMessage()
    
    def onSelectAddressGPS (self, evt):
        w = evt.widget
        value = w.get()
        with lock:
            config['GPS1']['Address'] = value
        while "GPS" in self.errMsgSource: self.errMsgSource.remove("GPS")
        desc = self.comPortDescriptions.get(value, 0)
        if desc:
            self.GPSDescLab.configure(text=desc)
        else:
            self.GPSDescLab.configure(text="")
        self.GPSQualityVal.set(0)
        self.X1Val.set(0.0)
        self.Y1Val.set(0.0)
        
        self.restartGPS1Flag.set()
        self.lastGPS1Time = datetime.datetime.now() 
        self.saveConfig()
        self.clearMessage()


    def hasGPSError (self):
        return "GPS" in self.errMsgSource
    
    def onSelectModeEM (self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except:
            pass
        with lock:
            config['EM']['Mode'] = value
        self.doEMUI(self.frame3a)
        if (value == "Serial"):
            currentCOMPorts = self.getAddresses("Serial")
            self.EMCbBx.configure(values = currentCOMPorts)
            if (config['EM']['Address'] not in currentCOMPorts):
                config['EM']['Address'] = currentCOMPorts[0]
            desc = self.comPortDescriptions.get(config['EM']['Address'], 0)
            if desc:
                self.EMDescLab.configure(text=desc) 
            else:
                self.EMDescLab.configure(text="")
        if (value == "Bluetooth"):
            currentBTNames = self.getAddresses("Bluetooth")
            self.EMCbBx.configure(values = currentBTNames)
            if (config['EM']['Address'] not in currentBTNames):
                config['EM']['Address'] = currentBTNames[0]
            desc = self.BTPortDescriptions.get(config['EM']['Address'], 0)
            if desc:
                self.EMDescLab.configure(text=desc) 
            else:
                self.EMDescLab.configure(text="")

        self.restartEMFlag.set()
        self.lastEMTime = datetime.datetime.now() 
        self.saveConfig()
        self.clearMessage()

    def onSelectAddressEM (self, evt):
        value = "Undefined"
        try:
            w = evt.widget
            value = w.get()
        except:
            pass
        with lock:
            config['EM']['Address'] = value

        desc = ""
        if (config['EM']['Mode'] == "Serial"):
            desc = self.comPortDescriptions.get(value, 0)
        if (config['EM']['Mode'] == "Bluetooth"):
            desc = self.BTPortDescriptions.get(value, 0)
            
        if desc:
            self.EMDescLab.configure(text=desc)
        else:
            self.EMDescLab.configure(text="")

        self.restartEMFlag.set()
        self.lastEMTime = datetime.datetime.now() 
        self.saveConfig()
        self.clearMessage()

    def onSelectBaudEM(self, evt):
        value = "38400"
        try:
            value = evt.widget.get()
        except:
            pass
        with lock:
            config['EM']['Baud'] = value
        self.restartEMFlag.set()
        self.saveConfig()

    def onSelectBaudGPS(self, evt):
        value = "38400"
        try:
            value = evt.widget.get()
        except:
            pass
        with lock:
            config['GPS1']['Baud'] = value
        self.restartGPS1Flag.set()
        self.saveConfig()

    def onHistBtnPressed(self):
        self.frame4.configure(text="Histogram")
        self.chartMode = "Histogram"
        self.clearChart()
        self.recalcEMDistn(forceRedraw = True)
        if (len(self.EMRec[self.EMHistCurr]) > 20):
            cx, cy = self.wToC(self.EMRec[self.EMHistCurr][-1], self.trackMaxY)
            if self.hist_bar is not None:
                self.canvas.delete(self.hist_bar)
            if cx is not None:
                self.hist_bar = self.canvas.create_rectangle(cx-5, 0, cx+5, cy, fill="red", outline = "", tags="bar")

    def onTrackBtnPressed(self):
        self.frame4.configure(text="Track")
        self.chartMode = "Track"
        self.clearChart()
        self.recalcTrackExtents(forceRedraw = True)
        if len(self.coords) > 0:
            coord = self.coords[-1]
            cx, cy = self.wToC(coord[0], coord[1])
            if cx is not None:
                self.canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill="red", outline = "", tags="point")


    def onSelectChartHist(self, evt):
        if (self.chartMode == "Histogram"):
            value = "Undefined"
            try:
                w = evt.widget
                value = w.get()
            except:
                pass
            if value != "Undefined":
                self.EMHistCurr = value
                self.clearChart()
                self.recalcEMDistn(forceRedraw = True)
                if (len(self.EMRec[self.EMHistCurr]) > 20):
                    cx, cy = self.wToC(self.EMRec[self.EMHistCurr][-1], self.trackMaxY)
                    if self.hist_bar is not None:
                        self.canvas.delete(self.hist_bar)
                    if cx is not None:
                        self.hist_bar = self.canvas.create_rectangle(cx-5, 0, cx+5, cy, fill="red", outline = "", tags="bar")

    # Ensure we dont get too many bells
    def ringTheBell (self):
        if (datetime.datetime.now() - self.lastBellTime).total_seconds() > 5:
            root.bell()
            self.lastBellTime = datetime.datetime.now()

    def showMessage(self, text, isSevere = False):
        self.lastErrorTime = datetime.datetime.now()
        self.ringTheBell()
        if (self.errMsgText != ""):
            if not text in self.errMsgText:
                self.errMsgText = self.errMsgText + "\n" + text
        else:
            self.errMsgText = text

        self.errMsg.configure(text=self.errMsgText, background="red", foreground="white")
        self.errMsg.place(relx=0.5, rely=0.25, relwidth=0.5, relheight=0.5)

    def clearMessage(self):
        if (self.errMsgText != ""):
            self.errMsgText = ""
            self.errMsg.configure( text="",background=root.cget("bg"), foreground="black")
            self.errMsg.place_forget()
        

    def hasEMError (self):
        return "EM" in self.errMsgSource

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
            if (datetime.datetime.now() - self.lastErrorTime).total_seconds() > 10:
                self.clearMessage()
                while "GPS" in self.errMsgSource: self.errMsgSource.remove("GPS")
                while "EM" in self.errMsgSource: self.errMsgSource.remove("EM")

            if not self.hasGPSError() and \
                    config['GPS1']['Mode'] != "Undefined" and \
                    (datetime.datetime.now() - self.lastGPS1Time).total_seconds() > 5:
                self.showMessage("GPS Timeout")
                self.errMsgSource.append("GPS")
                self.restartGPS1Flag.set()

            if not self.hasEMError() and \
                    config['EM']['Mode'] != "Undefined" and \
                    (datetime.datetime.now() - self.lastEMTime).total_seconds() > 5:
                self.showMessage("EM Timeout")
                self.errMsgSource.append("EM")
                self.restartEMFlag.set()

            # Ensure new devices are added to the combobox
            if (hasattr(self, "GPSLstBx")):
                if config['GPS1']['Mode'] != "Undefined":
                    oldAddresses = self.GPSLstBx.cget('values')
                    newAddresses = self.getAddresses(config['GPS1']['Mode'])
                    if (oldAddresses != newAddresses):
                        self.GPSLstBx.config(values=newAddresses)
                else:
                    self.GPSLstBx.set("")
                    self.GPSLstBx.configure(values=[])

            if hasattr(self, "EMCbBx"):
                if config['EM']['Mode'] != "Undefined":
                    oldAddresses = self.EMCbBx.cget('values')
                    newAddresses = self.getAddresses(config['EM']['Mode'])
                    if (oldAddresses != newAddresses):
                        self.EMCbBx.config(values=newAddresses)
                else:
                    self.EMCbBx.set("")
                    self.EMCbBx.configure(values = [])

        except Exception as e:
            print("Monitor: " + e)
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
        self.recordEM(self.EM_PRPHVal.get(),self.EM_PRP1Val.get(), self.EM_PRP2Val.get(), 
                       self.EM_HCPHVal.get(), self.EM_HCP1Val.get(), self.EM_HCP2Val.get())

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

        self.markTrack(self.X1Val.get(), self.Y1Val.get(), forceRedraw = True)
        self.recordEM(self.EM_PRPHVal.get(),self.EM_PRP1Val.get(), self.EM_PRP2Val.get(), 
                       self.EM_HCPHVal.get(), self.EM_HCP1Val.get(), self.EM_HCP2Val.get(), forceRedraw = True)

    def clearTracks(self):
        self.coords = []
        self.clearChart()

    def clearChart(self):
        #print("Cleared chart")
        self.chartStamp = datetime.datetime.now() - datetime.timedelta(seconds=30)
        self.trackMinX = self.trackMinY = 10000
        self.trackMaxX = self.trackMaxY = -10000
        self.canvasWidth = self.canvasHeight = 0
        for id in self.canvas.find_withtag("bar"):
            self.canvas.delete(id)
        for id in self.canvas.find_withtag("point"):
            self.canvas.delete(id)

    # record an EM sample
    def recordEM(self, EM_PRPHVal,EM_PRP1Val, EM_PRP2Val, EM_HCPHVal, EM_HCP1Val, EM_HCP2Val, forceRedraw = False):
        self.EMRec['PRPH'].append(EM_PRPHVal)
        self.EMRec['PRP1'].append(EM_PRP1Val)
        self.EMRec['PRP2'].append(EM_PRP2Val)
        self.EMRec['HCPH'].append(EM_HCPHVal)
        self.EMRec['HCP1'].append(EM_HCP1Val)
        self.EMRec['HCP2'].append(EM_HCP2Val)
        if (self.chartMode == "Histogram"):
            self.recalcEMDistn(forceRedraw) 
            cx, cy = self.wToC(self.EMRec[self.EMHistCurr][-1], self.trackMinY)
            if self.hist_bar is not None:
                self.canvas.delete(self.hist_bar)
            if cx is not None:
                self.hist_bar = self.canvas.create_rectangle(cx-5, 0, cx+5, cy, fill="red", outline = "", tags="bar")

    # mark and record point on the canvas window
    def markTrack(self, X, Y, forceRedraw = False):
        self.coords.append([X, Y])
        if (self.chartMode == "Track"):
            self.recalcTrackExtents(forceRedraw) 
            cx, cy = self.wToC(X, Y)
            if cx is not None:
                self.canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill="red", outline = "", tags="point")

    def recalcTrackExtents(self, forceRedraw = False):
        if (len(self.coords) < 2): return
        if (self.chartMode != "Track"): return
        if not forceRedraw and ((datetime.datetime.now() - self.chartStamp).total_seconds() < 30):
            return

        self.trackMinX = self.trackMinY = 10000
        self.trackMaxX = self.trackMaxY = -10000
        for coord in self.coords:
            if coord[0] < self.trackMinX:
                self.trackMinX = coord[0]
            if coord[0] > self.trackMaxX:
                self.trackMaxX = coord[0]
            if coord[1] < self.trackMinY:
                self.trackMinY = coord[1]
            if coord[1] > self.trackMaxY:
                self.trackMaxY = coord[1]

        self.canvasWidth = int(self.canvas.cget("width"))
        self.canvasHeight = int(self.canvas.cget("height"))

        # fixme - we shouldn't display more than ~1000 points
        for id in self.canvas.find_withtag("point"):
            self.canvas.delete(id)
        didAPoint = False
        for long,lat in self.coords:
            cx, cy = self.wToC(long, lat)
            if cx is not None:
                self.canvas.create_oval(cx-5,cy-5,cx + 5, cy+5, fill="red", outline = "", tags="point")
                didAPoint = True

        if not didAPoint:
            self.canvas.create_text(self.canvasWidth/2, self.canvasHeight/2, text="No Movement", tags="point")

        self.canvas.create_text(self.canvasWidth/2, self.canvasHeight - 10, text=self.GPSQualityCode(), tags="point")

        self.chartStamp = datetime.datetime.now() 

    def recalcEMDistn(self, forceRedraw = False) :
        if (self.chartMode != "Histogram"): return
        
        if (len(self.EMRec[self.EMHistCurr]) < 20): return

        if not forceRedraw and ((datetime.datetime.now() - self.chartStamp).total_seconds() < 30):
            return
        
        hist, bins = np.histogram(self.EMRec[self.EMHistCurr], bins=20)
        self.canvasWidth = int(self.canvas.cget("width"))
        self.canvasHeight = int(self.canvas.cget("height"))
        self.trackMinX = bins[0]
        self.trackMinY = 0
        self.trackMaxX = bins[-1]
        self.trackMaxY = max(hist)

        for id in self.canvas.find_withtag("bar"): 
            self.canvas.delete(id)
        for i in range(0, len(bins) - 1):
            cx1, cy1 = self.wToC(bins[i], self.trackMinY)
            cx2, cy2 = self.wToC(bins[i+1], hist[i])
            if cx1 is not None:
                self.canvas.create_rectangle(cx1, cy1, cx2, cy2, fill="grey", outline = "black", tags="bar")
                if (i % 5 == 0):
                    self.canvas.create_text((cx1+cx2)/2, self.canvasHeight - self.marginY / 2, 
                                            text=str(round((bins[i] + bins[i+1])/2)), tags="bar")

        self.chartStamp = datetime.datetime.now()

    # X: longitude | EM counts 
    # Y: latitude  | bin counts 
    def wToC(self, X, Y):
        self.marginX = 0
        self.marginY = 30
        
        if (self.canvasWidth <= self.marginX or 
            self.canvasHeight <=  self.marginY or
            (self.trackMaxX - self.trackMinX) <= 0 or 
            (self.trackMaxY - self.trackMinY) <= 0): 
            return None, None

        deltaLong= X - self.trackMinX
        deltaLat = Y - self.trackMinY

        longRatio= deltaLong / (self.trackMaxX - self.trackMinX)
        latRatio = deltaLat / (self.trackMaxY- self.trackMinY)

        cx = max(0, min(self.canvasWidth, 
                        longRatio * (self.canvasWidth - self.marginX)))
        cy = self.canvasHeight - self.marginY - \
                max(0, min((self.canvasHeight- self.marginY), 
                           latRatio * (self.canvasHeight- self.marginY)))
        return cx, cy
    
    def clearEMRec(self):
        print("Cleared EM hist")
        self.EMRec = defaultdict(list)
        self.EMRec['PRPH'] = []
        self.EMRec['PRP1']= []
        self.EMRec['PRP2']= []
        self.EMRec['HCPH']= []
        self.EMRec['HCP1']= []
        self.EMRec['HCP2']= []
        self.hist_bar = None
        self.EMHistCurr ='PRPH'
        self.clearChart()

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
        print(splitlines)
        if useGPS and len(splitlines) >= 10 and ("GPGGA" in splitlines[0] or "GNGGA" in splitlines[0]):
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
            return 1
        elif useGPS and len(splitlines) >= 8 and "GPVTG" in splitlines[0]: # http://aprs.gids.nl/nmea/#vtg
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
            return 1
        elif len(splitlines) >= 6 and "PDLM1" in splitlines[0]:
            with lock:
                self.EM_HCP1Val.set(splitlines[2])   #HCP conductivity in mS/m
                self.EM_HCPI1Val.set(splitlines[3])  #HCP inphase in ppt
                self.EM_PRP1Val.set(splitlines[4])   #PRP conductivity in mS/m
                self.EM_PRPI1Val.set(splitlines[5].split('*')[0]) #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 6 and "PDLM2" in splitlines[0]:
            with lock:
                self.EM_HCP2Val.set(splitlines[2])      #HCP conductivity in mS/m
                self.EM_HCPI2Val.set(splitlines[3])     #HCP inphase in ppt
                self.EM_PRP2Val.set(splitlines[4])      #PRP conductivity in mS/m
                self.EM_PRPI2Val.set(splitlines[5].split('*')[0])      #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 6 and "PDLMH" in splitlines[0]:
            with lock:
                self.EM_HCPHVal.set(splitlines[2])      #HCP conductivity in mS/m
                self.EM_HCPIHVal.set(splitlines[3])     #HCP inphase in ppt
                self.EM_PRPHVal.set(splitlines[4])      #PRP conductivity in mS/m
                self.EM_PRPHIVal.set(splitlines[5].split('*')[0])      #PRP inphase in ppt
            return 1
        elif len(splitlines) >= 4 and "PDLMA" in splitlines[0]:
            with lock:
                self.EM_VoltsVal.set(float(splitlines[1]))
                self.EM_TemperatureVal.set(float(splitlines[2]))
                self.EM_PitchVal.set(float(splitlines[3]))
                self.EM_RollVal.set(float(splitlines[4].split('*')[0]))
            return 1
        return 0

    # The gps reader thread
    def gps1_read(self, cfgName):
        while not self.stopFlag.is_set():
            cfg = config[cfgName]
            if (cfg['Mode'] == "Undefined") | ("No devices" in cfg['Address']):
               self.lastGPS1Time = datetime.datetime.now()
            else:
                self.restartGPS1Flag.clear()
                self.lastGPS1Time = datetime.datetime.now()
                while "GPS" in self.errMsgSource: self.errMsgSource.remove("GPS")
                self.X1Val.set(0.0)
                self.Y1Val.set(0.0)
                self.H1Val.set(0.0)
                s = None
                try:
                    encoding = 'ascii'
                    line = ""
                    s = self.openComms(cfg)
                    while (not self.stopFlag.is_set()) and not self.restartGPS1Flag.is_set():
                        while (line.find('\n') < 0) and not self.restartGPS1Flag.is_set():
                            if (cfg['Mode'] == "Serial"):
                                if (s.in_waiting <= 0):
                                    time.sleep(0.01)
                                else:
                                    byt = s.read(s.in_waiting)
                                    line += str(byt, encoding) # serial "socket"
                            else:
                                try:
                                    line += str(s.recv(1), encoding)  # BT, IP socket - has timeout set
                                except socket.timeout as e:
                                    err = e.args[0]
                                    # this next if/else is a bit redundant, but illustrates how the
                                    # timeout exception is setup
                                    if err == 'timed out':
                                        time.sleep(1)
                                        print("timeout detected")
                                        continue
                                    else:
                                        raise e
                                #except socket.error as e:
                                #    # Something else happened, handle error, exit, etc.
                                #    print(e)
                                #else:
                                #    if len(msg) == 0:
                                #        print('orderly shutdown on server end')
                                #        sys.exit(0)
                                #    else:
                                #        # got a message do something :)

                        linedata = line[1:line.find('\n')]
                        line = line[line.find('\n')+1:]

                        if self.nmea_decode(linedata):
                            self.lastGPS1Time = datetime.datetime.now()

                except Exception as e:
                    self.showMessage("gps: " + str(e))
                    #self.showMessage("Can't open " + cfg['Address'])
                    self.errMsgSource.append("GPS")
                    pass
                if s is not None:
                    s.close()
            time.sleep(1)

    # The em reader thread
    def em1_read(self, cfgName):
        while not self.stopFlag.is_set():
            cfg = config[cfgName]
            self.lastEMTime = datetime.datetime.now()
            if (cfg['Mode'] == "Undefined") | ("No devices" in cfg['Address']):
                continue
            else:
                self.restartEMFlag.clear()
                while "EM" in self.errMsgSource: self.errMsgSource.remove("EM")
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
                self.EM_RollVal.set(0)
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

                        if self.nmea_decode(linedata, useGPS=False): # fixme: Only use dualEM gps signal if there's no alternative
                            self.lastEMTime = datetime.datetime.now()

                        ROLL = self.EM_RollVal.get()
                        if float(abs(ROLL)) > 20:
                            self.showMessage(' Roll angle: ' + str(ROLL))
                            self.errMsgSource.append("EM")

                        #print("stop= " + str(self.stopFlag.is_set()) + "," + "restart= " + str( self.restartEMFlag.is_set()))
                    # end while    
                except Exception as e:
                    self.showMessage(" EM: " + str(e))
                    #self.showMessage("Cant open " + cfg['Address'] )
                    self.errMsgSource.append("EM")
                    pass
                if (s is not None):
                    s.close()
            time.sleep(1)

    def checkComPorts(self):
        tempD = dict()
        try:
            for port in list_ports.comports():
                tempD[port.device] = port.description
        except:
            #print("Exception finding com ports")
            pass
        with lock:
            self.comPortDescriptions.clear()
            self.comPortDescriptions['Undefined'] = "Undefined"
            self.comPortDescriptions = tempD.copy()

    def checkBTPorts(self):
        if (platform.system() == "Windows"):
            args = ["powershell.exe",  "-ExecutionPolicy", "RemoteSigned", "-Command", r"-"]
            process = subprocess.Popen(args, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
            process.stdin.write(b"$bluetoothDevices = Get-WmiObject -Query \"SELECT * FROM Win32_PnPEntity WHERE PNPClass = 'Bluetooth'\" | Select-Object Name,HardwareID\r\n")
            process.stdin.write(b"foreach ($device in $bluetoothDevices) {  Write-Host \"$($device.Name),$($device.HardwareID)\" }\r\n")

            output = process.communicate()[0].decode("utf-8").split("\n")

            with lock:
                self.BTPortDescriptions.clear()
                self.BTPortDescriptions["Undefined"] = "Undefined"
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
                            self.BTPortDescriptions[s] = name
                    except:
                        pass
        else:

            self.BTPortDescriptions['00:12:6f:00:c1:fb'] = "DualEM278 long"
            self.BTPortDescriptions['34:c9:f0:86:62:9a'] = "DualEM292 short"
            self.BTPortDescriptions['b8:d6:1a:0d:9a:22'] = "Facet Rover-9A22"
            self.BTPortDescriptions['dd:ee:ff:aa:bb:cc'] = "Sample BT 1 (garbage)"

    def portDiscovery(self, id):
        while not self.stopFlag.is_set():
            try:
                # Check for new devices being plugged in
                self.checkBTPorts()
                self.checkComPorts()
            except:
                pass
            time.sleep(30)


    def getAddresses(self, currentMode ):
        if (currentMode == "IP"):
            return(config['IP']["Recent"])
        if (currentMode == "Serial"):
            return(self.getSerialAddresses())
        if (currentMode == "Bluetooth"):
            return(self.getBTAddresses())
        return([])

    def getBTAddresses(self):
        result = []
        for addr, name in self.BTPortDescriptions.items():
            result.append(name)
        
        return(result)

    def getSerialAddresses(self):
        result = []
        for addr, name in self.comPortDescriptions.items():
            result.append(addr)

        return(result)

    def saveConfig (self):
        old = config['IP']["Recent"].split(",")
        if (config["GPS1"]['Mode'] == "IP"):
            curr = config["GPS1"]['Address']
            if (not curr in old):
                config['IP']["Recent"] = config['IP']["Recent"] +"," + curr

        old = config['Serial']["Recent"].split(",")
        if (config["GPS1"]['Mode'] == "Serial"):
            curr = config["GPS1"]['Address']
            if (not curr in old):
                config['Serial']["Recent"] = config['Serial']["Recent"]+"," + curr
        if (config["EM"]['Mode'] == "Serial"):
            curr = config["EM"]['Address']
            if (not curr in old):
                config['Serial']["Recent"] = config['Serial']["Recent"]+"," + curr

        old = config['Bluetooth']["Recent"].split(",")
        if (config["GPS1"]['Mode'] == "Bluetooth"):
            curr = config["GPS1"]['Address']
            if (not curr in old):
                config['Bluetooth']["Recent"] = config['Bluetooth']["Recent"]+"," + curr
        if (config["EM"]['Mode'] == "Bluetooth"):
            curr = config["EM"]['Address']
            if (not curr in old):
                config['Bluetooth']["Recent"] = config['Bluetooth']["Recent"]+"," + curr

        with open('Dualem_and_GPS_datalogger.ini', 'w') as configfile:
            config.write(configfile)

app = None
root = None
def main():
    global root
    root = tk.Tk()
    root.geometry("625x625+50+50")
    app = EMApp()
    root.protocol("WM_DELETE_WINDOW", app.shutDown)

    root.mainloop()

if __name__ == '__main__':
    main()
