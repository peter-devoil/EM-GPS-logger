import serial
import socket
from serial.tools import list_ports
import os
import sys
#import pygarmin  # https://github.com/quentinsf/pygarmin/
#import pynmea2 # https://fishandwhistle.net/post/2016/using-pyserial-pynmea2-and-raspberry-pi-to-log-nmea-output/
import time
import threading
import datetime
import getpass
import configparser

from tendo import singleton

import tkinter as tk
from tkinter import ttk

# 
me = singleton.SingleInstance()

# Use Windows Device Manager to find ports on each system
config = configparser.ConfigParser()
if not os.path.exists('Dualem_and_GPS_data_log.ini'):
    config['GPS1'] = {'Port': 'Undefined', 'Baud': 4800} # COM8
    config['GPS2'] = {'IPAddr': 'Undefined', 'IPPort': 5718} # COM8
    config['EM'] = {'Port': 'Undefined', 'Baud': 38400} # COM4
    config['Operator'] = {'Name' : getpass.getuser()}
else:
    config.read('Dualem_and_GPS_data_log.ini')

def saveConfig ():
    with open('Dualem_and_GPS_data_log.ini', 'w') as configfile:
        config.write(configfile)

lock = threading.Lock()

def dm(x):
    degrees = int(x) // 100
    minutes = x - 100*degrees
    return degrees, minutes

def decimal_degrees(degrees, minutes):
    return degrees + minutes/60 

comPortDescriptions = {}

def getComPorts():
    comPortDescriptions.clear()

    result = ['Undefined','test']
    for port in list_ports.comports():
        result.append(port.device)
        comPortDescriptions[port.device] = port.description

    return(result)        


################## Initialisation here ##################

class EMApp(ttk.Frame):
    def __init__(self):
        super().__init__()
        self.initUI()

        # Setting this flag will stop the reader threads
        self.stopFlag = threading.Event()
        self.restartEMFlag = threading.Event()
        self.restartGPS1Flag = threading.Event()
        self.restartGPS2Flag = threading.Event()

        self.workers = []
        self.thread1 = threading.Thread(target=self.gps1_read, args=('GPS1',), daemon = True)
        self.thread1.start()
        self.workers.append(self.thread1)
        self.lastGPS1Time = datetime.datetime.now()

        self.thread2 = threading.Thread(target=self.gps2_read, args=('GPS2',), daemon = True)
        self.thread2.start()
        self.workers.append(self.thread2)
        self.lastGPS2Time = datetime.datetime.now()

        self.EMThread = threading.Thread(target=self.em1_read, args=('EM',), daemon = True)
        self.EMThread.start()
        self.workers.append(self.EMThread)
        self.lastEMTime = datetime.datetime.now()

        self.numGP1Errors = 0
        self.numGP2Errors = 0
        self.numEMErrors = 0

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
        self.saveFile = tk.StringVar()
        self.saveFile.set(os.getcwd() + '/' + "Em38.All.PW.ISW.csv")
        sfLab = ttk.Label(frame1, text="All Data") 
        sfLab.grid(row=0, column = 0, sticky=tk.E, pady=5)
        saveFileEnt = ttk.Entry(frame1, textvariable=self.saveFile, width=80) 
        saveFileEnt.grid(row=0, column = 1, columnspan=2, sticky=tk.W, pady=5)

        self.savePlotFile = tk.StringVar()
        self.savePlotFile.set(os.getcwd() + '/' + "Em38.Plot.PW.ISW.csv")
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
        frame2 = ttk.LabelFrame(self, text="Position")
        frame2.grid(row=1, column = 0, columnspan=2, sticky=tk.W+tk.E+tk.N)

        # GPS1
        self.frame2a = ttk.Frame(frame2, style="CommOK.TFrame")
        self.frame2a.grid(row=0, column = 0, columnspan=4, pady=5, sticky=tk.W+tk.E)
        self.GP1Lab = ttk.Label(self.frame2a, text="Port 1", style="CommOK.TLabel") 
        self.GP1Lab.grid(row=0, column = 0, padx=5)
        self.GP1LstBx = ttk.Combobox(self.frame2a, values=getComPorts(), width=15, style="CommOK.TCombobox")
        self.GP1LstBx.set(config['GPS1']['Port'])

        self.GP1LstBx.bind('<<ComboboxSelected>>', self.onSelectGP1)
        self.GP1LstBx.grid(row=0, column = 1, padx=5)
        self.GP1DescLab = ttk.Label(self.frame2a, text="", style="CommOK.TLabel") 
        desc = comPortDescriptions.get(config['GPS1']['Port'], 0)
        if desc:
            self.GP1DescLab.configure(text=desc)
        self.GP1DescLab.grid(row=0, column = 2, columnspan=2, padx=5, sticky=tk.W+tk.E)

        XLab = ttk.Label(frame2, text="Lng") 
        XLab.grid(row=1, column = 0, pady=5)
        self.X1Val = tk.DoubleVar()
        self.X1Val.set(0.0)
        XEnt = ttk.Entry(frame2, textvariable=self.X1Val) 
        XEnt.grid(row=1, column = 1, pady=5)

        YLab = ttk.Label(frame2, text="Lat") 
        YLab.grid(row=1, column = 2, pady=5)
        self.Y1Val = tk.DoubleVar()
        self.Y1Val.set(0.0)
        YEnt = ttk.Entry(frame2, textvariable=self.Y1Val) 
        YEnt.grid(row=1, column = 3, pady=5)

        self.H1Val = tk.DoubleVar()  # not displayed
        self.H1Val.set(0.0)

        # GPS2
        self.frame2b = ttk.Frame(frame2)
        self.frame2b.grid(row=2, column = 0, columnspan=4, pady=5, sticky=tk.W+tk.E)
        self.GP2Lab = ttk.Label(self.frame2b, text="IP Address", style="CommOK.TLabel") 
        self.GP2Lab.grid(row=0, column = 0, padx=5)

        self.GP2IPAddr = tk.StringVar()
        self.GP2IPAddr.set(config['GPS2']['IPAddr'])
        self.GP2IPAddrEntry = ttk.Entry(self.frame2b, textvariable=self.GP2IPAddr) 
        self.GP2IPAddr.trace_add("write", self.onChangedGP2)
        self.GP2IPAddrEntry.grid(row=0, column = 1, padx=5)

        self.GP2Lab2 = ttk.Label(self.frame2b, text="Port", style="CommOK.TLabel") 
        self.GP2Lab2.grid(row=0, column = 2, padx=5)
        self.GP2IPPort = tk.StringVar()
        self.GP2IPPort.set(config['GPS2']['IPPort'])
        self.GP2IPPortEntry = ttk.Entry(self.frame2b, textvariable=self.GP2IPPort) 
        self.GP2IPPort.trace_add("write", self.onChangedGP2)
        self.GP2IPPortEntry.grid(row=0, column = 3, padx=5)

        XLab = ttk.Label(frame2, text="Lng") 
        XLab.grid(row=3, column = 0, pady=5)
        self.X2Val = tk.DoubleVar()
        self.X2Val.set(0.0)
        XEnt = ttk.Entry(frame2, textvariable=self.X2Val) 
        XEnt.grid(row=3, column = 1, pady=5)

        YLab = ttk.Label(frame2, text="Lat") 
        YLab.grid(row=3, column = 2, pady=5)
        self.Y2Val = tk.DoubleVar()
        self.Y2Val.set(0.0)
        YEnt = ttk.Entry(frame2, textvariable=self.Y2Val) 
        YEnt.grid(row=3, column = 3, pady=5)

        self.H2Val = tk.DoubleVar()  # not displayed
        self.H2Val.set(0.0)

        # EM info
        frame3 = ttk.LabelFrame(self, text="EM")
        frame3.grid(row=2, column = 0, columnspan=2, sticky=tk.W+tk.E+tk.S)
        
        self.frame3a = ttk.Frame(frame3)
        self.frame3a.grid(row=0, column = 0, columnspan=8, pady=5, sticky=tk.W+tk.E)
        self.EMLab = ttk.Label(self.frame3a, text="Port", style="CommOK.TLabel") 
        self.EMLab.grid(row=0, column = 0, padx=5)
        self.EMCbBx = ttk.Combobox(self.frame3a, values=getComPorts(), width=15, style="CommOK.TCombobox")
        self.EMCbBx.set(config['EM']['Port'])

        self.EMCbBx.bind('<<ComboboxSelected>>', self.onSelectEM)
        self.EMCbBx.grid(row=0, column = 1, padx=5)
        self.EMDescLab = ttk.Label(self.frame3a, text="") 
        desc = comPortDescriptions.get(config['EM']['Port'], 0)
        if desc:
            self.EMDescLab.configure(text=desc)

        self.EMDescLab.grid(row=0, column = 2, padx=5, sticky=tk.W+tk.E, columnspan=6)

        frame3b = ttk.Frame(frame3)
        frame3b.grid(row=1, column = 0, columnspan=8, pady=5, sticky=tk.W)
        TempLab = ttk.Label(frame3b, text="Temperature", style="CommOK.TLabel") 
        TempLab.grid(row=0, column = 0, pady=5)
        self.EM_TemperatureVal= tk.DoubleVar()
        self.EMTemperature = ttk.Label(frame3b, textvariable=self.EM_TemperatureVal) 
        self.EMTemperature.grid(row=0, column = 1, padx=5)


        self.D025Lab = ttk.Label(frame3, text="025", style="CommOK.TLabel") 
        self.D025Lab.grid(row=2, column = 0, pady=5)
        self.EM_PRPHVal = tk.DoubleVar()
        self.EM_PRPHIVal = tk.DoubleVar()
        D025Ent = ttk.Entry(frame3, textvariable=self.EM_PRPHIVal, width=8) 
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
        self.D075Lab.grid(row=2, column = 6, pady=5)
        self.EM_HCPHVal = tk.DoubleVar()
        self.EM_HCPIHVal = tk.DoubleVar()
        D075Ent = ttk.Entry(frame3, textvariable=self.EM_HCPHVal, width=8) 
        D075Ent.grid(row=2, column = 7, pady=5)
        
        self.D15Lab = ttk.Label(frame3, text="15", style="CommOK.TLabel") 
        self.D15Lab.grid(row=2, column = 8, pady=5)
        self.EM_HCP1Val = tk.DoubleVar()
        self.EM_HCPI1Val = tk.DoubleVar()
        D15Ent = ttk.Entry(frame3, textvariable=self.EM_HCP1Val, width=8) 
        D15Ent.grid(row=2, column = 9, pady=5)

        self.D30Lab = ttk.Label(frame3, text="30", style="CommOK.TLabel") 
        self.D30Lab.grid(row=2, column = 10, pady=5)
        self.EM_HCP2Val = tk.DoubleVar()
        self.EM_HCPI2Val = tk.DoubleVar()
        D30Ent = ttk.Entry(frame3, textvariable=self.EM_HCP2Val, width=8) 
        D30Ent.grid(row=2, column = 11, pady=5)

       # Undisplayed 
        self.TrackVal= tk.DoubleVar()
        self.SpeedVal= tk.DoubleVar()
        self.EM_VoltsVal= tk.DoubleVar()
        self.EM_PitchVal= tk.DoubleVar()
        self.EM_RollVal= tk.DoubleVar()

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

        self.monitor = root.after(250, self.doMonitor)

    def onSelectGP1 (self, evt):
        w = evt.widget
        value = w.get()
        config['GPS1']['Port'] = value
        self.frame2a.configure(style="CommOK.TFrame")
        self.GP1Lab.configure(style="CommOK.TLabel")
        self.GP1LstBx.configure(style="CommOK.TCombobox")
        desc = comPortDescriptions.get(value, 0)
        if desc:
            self.GP1DescLab.configure(text=desc, style="CommOK.TLabel")
        else:
            self.GP1DescLab.configure(text="", style="CommOK.TLabel")
        
        self.restartGPS1Flag.set()
        self.lastGPS1Time = datetime.datetime.now() 
        saveConfig()

    def onGP1Error (self, msg):
        self.frame2a.configure(style="CommError.TFrame")
        self.GP1Lab.configure(style="CommError.TLabel")
        self.GP1LstBx.configure(style="CommError.TCombobox")
        self.GP1DescLab.configure(text=msg, style="CommError.TLabel")

    def onGP1NoError (self):
        s = self.frame2a.cget("style")
        if (s != "CommOK.TFrame" ):
            self.frame2a.configure(style="CommOK.TFrame")
            self.GP1Lab.configure(style="CommOK.TLabel")
            self.GP1LstBx.configure(style="CommOK.TCombobox")
            self.GP1DescLab.configure(text="", style="CommOK.TLabel")

    def hasGP1Error (self):
        s = self.frame2a.cget("style")
        if (s != "CommOK.TFrame" ):
            return True
        return False

    def onChangedGP2 (self, var, index, mode):
        config['GPS2']['IPAddr'] = self.GP2IPAddr.get()
        config['GPS2']['IPPort'] = self.GP2IPPort.get()
        self.frame2b.configure(style="CommOK.TFrame")
        self.GP2Lab.configure(style="CommOK.TLabel")
        self.GP2IPAddrEntry.configure(style="CommOK.TEntry")
        self.GP2IPPortEntry.configure(style="CommOK.TEntry")
#        desc = comPortDescriptions.get(value, 0)
#        if desc:
#            self.GP2DescLab.configure(text=desc, style="CommOK.TLabel")
#        else:
#            self.GP2DescLab.configure(text="", style="CommOK.TLabel")
        
        self.restartGPS2Flag.set()
        self.lastGPS2Time = datetime.datetime.now() 
        saveConfig()

    def onGP2Error (self, msg):
        self.frame2b.configure(style="CommError.TFrame")
        self.GP2Lab.configure(style="CommError.TLabel")
        self.GP2Lab2.configure(style="CommError.TLabel")
        self.GP2IPAddrEntry.configure(style="CommError.TEntry")
        self.GP2IPPortEntry.configure(style="CommError.TEntry")

    def onGP2NoError (self):
        s = self.frame2b.cget("style")
        if (s != "CommOK.TFrame" ):
            self.frame2b.configure(style="CommOK.TFrame")
            self.GP2Lab.configure(style="CommOK.TLabel")
            self.GP2Lab2.configure(style="CommOK.TLabel")
            self.GP2IPAddrEntry.configure(style="CommOK.TEntry")
            self.GP2IPPortEntry.configure(style="CommOK.TEntry")

    def hasGP2Error (self):
        s = self.frame2b.cget("style")
        if (s != "CommOK.TFrame" ):
            return True
        return False

    def onSelectEM (self, evt):
        w = evt.widget
        value = w.get()
        config['EM']['Port'] = value
        desc = comPortDescriptions.get(value, 0)
        self.frame3a.configure(style="CommOK.TFrame")
        self.EMLab.configure(style="CommOK.TLabel")
        self.EMCbBx.configure(style="CommOK.TCombobox")
        if desc:
            self.EMDescLab.configure(text=desc, style="CommOK.TLabel")
        else:
            self.EMDescLab.configure(text="", style="CommOK.TLabel")

        self.restartEMFlag.set()
        self.lastEMTime = datetime.datetime.now() 
        saveConfig()

    def onEMError (self, msg):
        self.frame3a.configure(style="CommError.TFrame")
        self.EMLab.configure(style="CommError.TLabel")
        self.EMCbBx.configure(style="CommError.TCombobox")
        self.EMDescLab.configure(text=msg, style="CommError.TLabel")

    def onEMNoError (self):
        s = self.frame3a.cget("style")
        if (s != "CommOK.TFrame" ):
            self.frame3a.configure(style="CommOK.TFrame")
            self.EMLab.configure(style="CommOK.TLabel")
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
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Longitude 1,Latitude 1,Elevation 1,Longitude 2,Latitude 2,Elevation 2,Speed 2,Track 2,EM PRP1,EM PRP2,EM PRPH,EM HCP1,EM HCP2,EM HCPH,EM PRPI1,EM PRPI2,EM PRPIH,EM HCPI1,EM HCPI2,EM HPCIH,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=' + str(self.operator.get()) + '\n')
        self.doLogging()

    def pauseLogging(self):
        if (self.running != None):
            root.after_cancel(self.running)
            self.running = None

    def doMonitor(self):
        try:
            if (datetime.datetime.now() - self.lastGPS1Time).total_seconds() > 2:
                self.onGP1Error("Timeout")

            if (self.hasGP1Error()):
                self.numGP1Errors += 1

            if (self.numGP1Errors > 10):
                self.onGP1NoError()
                self.numGP1Errors = 0

            if (datetime.datetime.now() - self.lastGPS2Time).total_seconds() > 2:
                self.onGP2Error("Timeout")

            if (self.hasGP2Error()):
                self.numGP2Errors += 1

            if (self.numGP2Errors > 10):
                self.onGP2NoError()
                self.numGP2Errors = 0

            if (datetime.datetime.now() - self.lastEMTime).total_seconds() > 2:
                if (not self.hasEMError()):
                    self.onEMError("Timeout")
                    self.restartEMFlag.set()

            if (self.hasEMError()):
                self.numEMErrors += 1

            if (self.numEMErrors > 10):
                self.onEMNoError()
                self.numEMErrors = 0

        except Exception as e:
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
            pass

        oldComports = self.GP1LstBx.cget('values')
        newComports = getComPorts()
        if (oldComports != newComports):
            #print("old= + %s" % (oldComports,))
            self.GP1LstBx.config(values=newComports)
            self.EMCbBx.config(values=newComports)

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
            str(self.X2Val.get()) + "," + str(self.Y2Val.get()) + "," + str(self.H2Val.get()) + "," + \
            str(self.SpeedVal.get()) + "," + str(self.TrackVal.get()) + \
                self.getE1() + \
                '\n'
        with open(self.saveFile.get(), 'a') as the_file:
            the_file.write(line)
            the_file.flush()

    # Write to the plot file 
    def doitPlot(self):
        if not os.path.exists(self.savePlotFile.get()):
            with open(self.savePlotFile.get(), 'w') as the_file:
               the_file.write('YYYY-MM-DD,HH:MM:SS.F,Plot,Longitude 1,Latitude 1,Height 1,Longitude 2,Latitude 2,Height 2,E1_PRP1,E1_PRP2,E1_PRPH,E1_HCP1,E1_HCP2,E1_HCPH,E1_PRPI1,E1_PRPI2,E1_PRPIH,E1_HCPI1,E1_HCPI2,E1_HCPIH,E1_Volts,E1_Temperature,E1_Pitch,E1_Roll,Operator=' + str(self.operator.get()) + '\n')
        time_now = datetime.datetime.now().strftime('%Y-%m-%d,%H:%M:%S.%f')
        line = time_now + "," + self.SeqVal.get() + "," +\
            str(self.X1Val.get()) + "," + str(self.Y1Val.get()) + "," + str(self.H1Val.get()) + "," + \
            str(self.X2Val.get()) + "," + str(self.Y2Val.get()) + "," + str(self.H2Val.get()) + \
            self.getE1() + \
            '\n'

        with open(self.savePlotFile.get(), 'a') as the_file:
            the_file.write(line)
            the_file.flush()

    # The gps reader thread
    def gps1_read(self, cfgName):
        cfg = config[cfgName]
        while not self.stopFlag.is_set():
            if cfg['Port'] == "Undefined":
               self.lastGPS1Time = datetime.datetime.now()
            else:
                s = None
                try:
                    self.restartGPS1Flag.clear()
                    self.X1Val.set(0.0)
                    self.Y1Val.set(0.0)
                    self.H1Val.set(0.0)

                    s = serial.Serial(cfg['Port'], cfg['Baud'])
                    #s.write(b'%') 
                    while (not self.stopFlag.is_set() ) & (not self.restartGPS1Flag.is_set()):
                        line = s.readline() 
                        # nonblocking read()? - https://stackoverflow.com/questions/38757906/python-3-non-blocking-read-with-pyserial-cannot-get-pyserials-in-waiting-pro/
                        #print("line = " + line)
                        linedata = str(line)[2:]
                        splitlines = linedata.split(',')
    
                        if "GPGGA" in linedata:
                            S = decimal_degrees(*dm(float(splitlines[2])))
                            if splitlines[3].find('S') >= 0:
                                S = S * -1
                            E = decimal_degrees(*dm(float(splitlines[4])))
                            H = float(splitlines[9])
                            with lock:
                                self.X1Val.set(E)
                                self.Y1Val.set(S)
                                self.H1Val.set(H)
                                #print("X= " + str(self.XVal.get()))
                            self.lastGPS1Time = datetime.datetime.now()
                except Exception as e:
                    if hasattr(e, 'message'):
                        self.onGP1Error("Exception opening " + cfg['Port'] + e.message)
                    else:
                        self.onGP1Error("Exception opening " + cfg['Port'])
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

    # The gps reader thread
    def gps2_read(self, cfgName):
        cfg = config[cfgName]
        while not self.stopFlag.is_set():
            if cfg['IPAddr'] == "Undefined":
               self.lastGPS2Time = datetime.datetime.now()
            else:
                s = None
                try:
                    self.restartGPS2Flag.clear()
                    self.X2Val.set(0.0)
                    self.Y2Val.set(0.0)
                    self.H2Val.set(0.0)

                    cfg = config[cfgName]
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect((cfg['IPAddr'], int(cfg['IPPort'])))
                    # s.write(b'%\r\n') 
                    #print("opened")
                    while (not self.stopFlag.is_set()) & (not self.restartGPS2Flag.is_set()):
                        line = self.buffered_readLine(s)
                        #print("line = " + line)
                        linedata = str(line)[1:]
                        splitlines = linedata.split(',')

                        if "GPGGA" in linedata:
                            S = decimal_degrees(*dm(float(splitlines[2])))
                            E = decimal_degrees(*dm(float(splitlines[4])))
                            H = float(splitlines[9])
                            with lock:
                                self.X2Val.set(E)
                                self.Y2Val.set(S)
                                self.H2Val.set(H)
                                #print("X= " + str(self.XVal.get()))
                            self.lastGPS2Time = datetime.datetime.now()
                        if "GPVTG" in linedata: # http://aprs.gids.nl/nmea/#vtg
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
                            self.lastGPS2Time = datetime.datetime.now()
                    if s is not None:        
                        s.close()
                except Exception as e:
                    if hasattr(e, 'message'):
                        print("Exception opening " + cfg['IPAddr'] + e.message)
                    else:
                        print("Exception opening " + cfg['IPAddr'])
                    pass
            time.sleep(1)


    # The em reader thread
    def em1_read(self, cfgName):
        cfg = config[cfgName]
        while not self.stopFlag.is_set():
            if cfg['Port'] == "Undefined":
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
                    print("Opening " + cfg['Port'] + '\n') 
                    s = serial.Serial(cfg['Port'], cfg['Baud'], timeout=2, write_timeout=2)
                    s.write(b'%\r\n') 
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
                    self.onEMError("Exception opening " + cfg['Port'] )
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
    root.geometry("600x500+200+200")
    app = EMApp()
    root.protocol("WM_DELETE_WINDOW", app.shutDown)

    root.mainloop()

if __name__ == '__main__':
    main()
