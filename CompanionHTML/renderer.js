'use strict';

//TODO


// This file is required by the index.html file and will
// be executed in the renderer process for that window.
// All of the Node.js APIs are available in this process.
var traceElement = document.querySelector('#trace');
var mapElement = document.querySelector('#map');
var msgElement = document.querySelector("#messages")

if (document.querySelector('#tabselect') !== null) {
    function hideElement(element) {
        element.style.display = 'none';
    }

    function showElement(element) {
        element.style.display = 'block';  
    }

    function tabToggled(e) {
        if (e.target.value == "map") {
            showElement(mapElement);
            hideElement(traceElement);
        } else if (e.target.value == "trace") {
            hideElement(mapElement);
            showElement(traceElement);
        }
    }
    document.querySelector("#tabselect")
        .addEventListener("change", (e) => tabToggled(e));

    window.addEventListener("load", (event) => {     
        hideElement(mapElement);
        showElement(traceElement);
    });

    window.addEventListener("resize", (event) => {     
        if (mapElement.style.display == "none") {
            element.style.display = 'block';
            myMap.initData(mapElement);
            element.style.display = 'none';
        }  else {
            myMap.initData(mapElement);
        }
        if (traceElement.style.display == "none") {
            traceElement.style.display = 'block';
            myTrace.initData(traceElement);
            traceElement.style.display = 'none';
        } else {
            myTrace.initData(traceElement);
        }
    });
}

var theData = {features: {features : [], type : "FeatureCollection"}, 
               status: {status: "", EM: "", Drone: ""}, 
               lowerBounds: [], 
               upperBounds: [],
               channels: []
           };

// how often to poll the rover for new data
var updateInterval = 1000; // milliseconds
var lastUpdateTime = Date.now();
var updateTimer = null; // timer ID that will update window contents / colour
var statusTimer = null; // "     "   for monitoring companion status

var pollingID = setTimeout(pollForMore, updateInterval);

myTrace.initData( traceElement );
myMap.initData( mapElement );

if (!Array.prototype.last){
    Array.prototype.last = function(){
        return this[this.length - 1];
    };
};

function isEqCT(x, y) {
    if (!isFinite(x) || !isFinite(y)) { return (false); }
    return(Math.abs(x - y) <  1.0E-6 /*Number.EPSILON*/);
}

let backoffDelay = 0;
async function pollForMore() {
    var since = 0
    try {
        var features = theData.features.features;
        if (features.length > 0) {
            since = features.last().properties.id;
        }
        var url = location.origin + "/getData?since=" + parseInt(since);
        var json = await fetch(url, { signal: AbortSignal.timeout(4000) })
            .then(res => res.json());
        if (json != null) updateData(json);
        lastUpdateTime = Date.now();
        backoffDelay = 0;
    } catch(err) { 
        if (err.name === "TimeoutError") {
            console.log("Polling Timeout");//fixme - show message
            backoffDelay = 5000;
        } else {
            // A network error, or some other problem.
            console.log(`Polling Error: type: ${err.name}, message: ${err.message}`); //fixme - show message
        }
    }
    pollingID = setTimeout(pollForMore, updateInterval + backoffDelay);
}

function stopInterval() {
    clearTimeout(pollingID);
}

function updateData (json) {
    var features = theData.features.features
    var lastid = 0;
    if (features.length > 0) {
        var x= features.last().properties;
        lastid = x.id;
    }

    json.data.forEach(r => {
        if (r.id > lastid) { 
            r.time = moment(r.timestamp, "yyyy-MM-dd,HH:mm:ss");
            Object.keys(r).forEach(k => {
                if (k.indexOf("EM_") >=0) {
                    r[k] = parseFloat(r[k]);
                }
            });
            var f = {"geometry" : {"coordinates": [parseFloat(r["X"]), parseFloat(r["Y"])], "type": "Point"},
                     "properties" : r};
            features.push(f);
        }
    });

    theData.status = json.status;

    //csv2geojson.csv2geojson(theData.data.slice(theData.features.length, theData.data.length), { latfield: 'Y',lonfield: 'X'}, 
    //csv2geojson.csv2geojson(theData.data, { latfield: 'Y',lonfield: 'X'}, 
    //        function(err, data) { 
    //            theData.features = data
    //});

    var newChannels = Object.keys(features[0].properties)
        .filter((c) => c.indexOf("EM_") >=0);

    newChannels.forEach(dataName => {
        if (!theData.channels.some(c2 => c2.dataName == dataName )) {
            var prettyName = dataName.replace("EM_", "")
            theData.channels.push({
                active: wasSelected(prettyName),
                dataName: dataName,
                displayName: prettyName
            });
        }
    });

    theData.channels.forEach( c => {
        if (typeof theData.lowerBounds[c.dataName] == "undefined") {
            theData.lowerBounds[c.dataName] = 1000000;
        }
        if (typeof theData.upperBounds[c.dataName] == "undefined") {
            theData.upperBounds[c.dataName] = -1000000;
        }
    });
    
    myTrace.addData( traceElement, theData );
    myMap.addData( mapElement, theData );
}

// Save the EM data to a file.
document.querySelector('#save_data')
    .addEventListener('click', async () => {
        if (typeof window.showSaveFilePicker === 'function') {
            // not firefox/safari, and not CORS
            var ok = false;
            var handle = {};
            try {
                handle = await window.showSaveFilePicker({
                    types: [
                        { description: "CSV", accept: { "text/csv": [".csv"] } }],
                    excludeAcceptAllOption: false,
                    suggestedName: "rootBotData.csv",
                    startIn: 'downloads'
                });
                ok = true;
            } catch (e) {
                console.log(e);
            }
            if (ok) {
                const newName = handle.name;
                const writable = await handle.createWritable();
                if (handle.name.endsWith(".csv")) {
                    await writable.write(assembleCSV());
                }
                // Close the file and write the contents to disk.
                await writable.close();
        }
        } else {
            console.log("opening new window");
            let encoded = encodeURIComponent(assembleCSV()); 
            var dataStr = "data:text/csv;charset=utf-8," + encoded;

            var dlAnchorElem = document.getElementById('downloadAnchorElem');
            dlAnchorElem.setAttribute("href", dataStr);
            dlAnchorElem.setAttribute("download", "rootBotData.csv");
            dlAnchorElem.click();
        }
});

function assembleCSV() {
   var csvHdr = 'YYYY-MM-DD,HH:MM:SS.F,Longitude,Latitude,Elevation,Speed,Track,Quality,EM PRP0,EM PRP1,EM PRP2,EM PRP4,EM HCP0,EM HCP1,EM HCP2,EM HCP4,EM PRPI0,EM PRPI1,EM PRPI2,EM PRPI4,EM HCPI0,EM HCPI1,EM HCPI2,EM HCPI4,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=Rootbot';
   var features = theData.features.features;
   var csvBody = features
       .filter(x => x.properties.recorded) 
       .map(f => {
            var p = f.properties;
            var line = [p.timestamp, p.X, p.Y, p.Z, p.Speed, p.Track, p.Quality].join(",") + "," +
                       [p.EM_PRP0, p.EM_PRP1, p.EM_PRP2, p.EM_PRP4, p.EM_HCP0, p.EM_HCP1, p.EM_HCP2, p.EM_HCP4,
                        p.EM_PRPI0, p.EM_PRPI1, p.EM_PRPI2, p.EM_PRPI4, p.EM_HCPI0, p.EM_HCPI1, p.EM_HCPI2, p.EM_HCPI4,
                        p.EM_Volts, p.EM_Temperature, p.EM_Pitch, p.EM_Roll].join(",");
            return(line);
         })
       .join("\n");

   return(csvHdr + "\n" + csvBody);
}

document.querySelector('#view_logs')
    .addEventListener('click', async () => {
        console.log("downloading logs");

        var url = location.origin + "/getLogs";
        var logData = await fetch(url, { signal: AbortSignal.timeout(10000) })
            .then(res => res.json());
        // fixme - check that it ran correctly

        var msg = "Error getting logs";
        if (logData != null) {
            msg = logData.stdout;
        }

        var dataStr = "data:text/plain;charset=utf-8," + msg;

        var dlAnchorElem = document.getElementById('downloadAnchorElem');
        dlAnchorElem.setAttribute("href", dataStr);
        dlAnchorElem.setAttribute("download", "rootBotLogs.txt");
        dlAnchorElem.click();
});

/*unused function convertToCSV(arr) {
    const array = [Object.keys(arr[0])].concat(arr)
    return array.map(it => {
        return Object.values(it).toString()
    }).join('\n')
}
*/

// Set a timer to monitor the last update time. Flash warnings if it's delayed.
updateTimer = setInterval( function() {
    var bgCol = "";
    var dt = Date.now() - lastUpdateTime;
    if(dt > 4000){
        bgCol = "#FF0000";
    } else if(dt > 2000) {
        bgCol = "#FFA500";
    }
    var lWin = document.querySelector("#lastUpdate");
    var old = lWin.style.backgroundColor;
    if (old != bgCol) {
        lWin.style.backgroundColor = bgCol;
    }
    lWin.innerText = "Last update: " + (Math.round(dt / 100) / 10) + "s";
}, 100);

// Monitor the remote status (will change with mission plan)
statusTimer = setInterval( async function() {
    var sBtn = document.querySelector("#startStop");
    var old = sBtn.toggled;

    var status = theData.status;

    var lbl = sBtn.children[1];

    if (status.status == "Running") {
        if (lbl.innerText != "Stop") {
            lbl.innerText = "Stop";
        }
        if (sBtn.toggled) {
            sBtn.toggled = false;
        }
    } else if (status.status == "Idle") {
        if (lbl.innerText != "Start") {
            lbl.innerText = "Start";
        }
        if (! sBtn.toggled) {
            sBtn.toggled = true;
        }
    }
    var sLbl = document.querySelector("#status");
    sLbl.innerHTML = "Status: " + (status.status == "Running" ? "Recording" : "Idle");

    var hasWarning = false;

    // roll indicator/warning
    try {
        var features = theData.features.features;
        if (features.length > 0) {
            var lastf = features[features.length - 1];
            if (Math.abs(lastf.properties.EM_Roll) > 10) { // will throw if no data
                sLbl.innerHTML += "<br>Roll = " + lastf.properties.EM_Roll;
                hasWarning = true;
            }
        }
    } catch (e) {
        console.log(e);
    }
    if (theData.status.EM != "Ok") {
        sLbl.innerHTML += "<br>EM Fault";
        hasWarning = true;
    }
    if (theData.status.GPS != "Ok") {
        sLbl.innerHTML += "<br>GPS Fault";
        hasWarning = true;
    }

    if(hasWarning) {
        var old = sLbl.style.backgroundColor;
        if (old != "#FF0000") {
            sLbl.style.backgroundColor = "#FF0000";
        }
    } else {
        if (sLbl.style.backgroundColor != "") {
            sLbl.style.backgroundColor = "";
        }
    }
}, 1000);

// Manually start/stop the recorder. Eventually, the polling loop will catch up
// fixme - should have a guard for repeated clicks
document.querySelector('#startStop')
   .addEventListener('click', async (event) => { 
      if(event.target.innerText == "Stop") {
           var url = location.origin + "/setStatus?status=Idle"
           fetch(url, { signal: AbortSignal.timeout(1000) });
      } else if(event.target.innerText == "Start") {
           var url = location.origin + "/setStatus?status=Running"
           fetch(url, { signal: AbortSignal.timeout(1000) });
      }
   });

let dialog = document.querySelector("#dialog");
document.querySelector("#close-button")
    .addEventListener("click", async () => {
        var url = location.origin + "/shutDown"; // fixme add a password to this
        var json = await fetch(url, { signal: AbortSignal.timeout(5000) });
        dialog.close();
});
document.querySelector("#cancel-button")
    .addEventListener("click", async () => {
        dialog.close();
});

document.querySelector('#powerOff')
   .addEventListener('click', async () => { 
        dialog.showModal(); 
   }
);


let drawer = document.querySelector("#channelDrawer");
drawer.addEventListener("toggle", (e) => drawerToggled(e) );

function drawerToggled (e) {
    if (e.target.id == "channelDrawer") {
        if (e.newState == "open") {
            var w = drawer.querySelectorAll(".chSel");
            w.forEach((cbx) => {
                var chan = theData.channels.find((c) => c.displayName == cbx.id);
                if (chan != null) { 
                    cbx.toggled = chan.active; 
                }
            })
        } else if (e.newState == "closed") {
//            var w = drawer.querySelectorAll(".chSel");
//            w.forEach(cbx => {
//                var chan = theData.channels.find(c => c.displayName == cbx.id);
//                if (chan != null) { chan.active = cbx.toggled; }
//            })
        }
    }
}


let channels = document.querySelectorAll(".chSel");
channels.forEach(element => {
   element.addEventListener("toggle", (cbx) => channelToggled(cbx) );
});

function channelToggled (e) {
    var prettyName = e.target.id;
    var chan = theData.channels.find(c => c.displayName == prettyName);
    if (chan) {
        chan.active = e.target.toggled;
    }
}

function wasSelected (prettyName) {
    var wasChecked = document.querySelector("#" + prettyName).toggled;
    return(wasChecked === true);
}

function saveChannels  () {
   var channels = theData.channels
      .filter(chan => chan.active)
      .map(n => n.displayName);
   localStorage.setItem('channels', JSON.stringify(channels));
}

function loadChannels  () {
   var channels = JSON.parse(localStorage.getItem('channels'));
   if (channels) {
      //document.querySelectorAll(".chSel").forEach(b => b.toggled = false);

      channels.forEach(dn => {
         document.querySelector("#" + dn).toggled = true;
      });
   } else {
      document.querySelectorAll(".chSel").forEach(b => b.toggled = true);
   }
}

let closeButton = document.querySelector("#channel-close-button");
closeButton.addEventListener("click", () => { drawer.close(); saveChannels() } );

//localStorage.setItem('channels', JSON.stringify( ["PRP0", "HCP0"] ));
customElements.whenDefined("x-checkbox").then(() => {loadChannels();});
