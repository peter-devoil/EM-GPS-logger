'use strict';

// This file is required by the index.html file and will
// be executed in the renderer process for that window.
// All of the Node.js APIs are available in this process.

var traceElement = document.querySelector('#trace');
var mapElement = document.querySelector('#map');
var msgElement = document.querySelector("#messages")
var split = Split(['#split-0', '#split-1'] /*, {onDragEnd: () => myHist.setupHist(histElement)}*/);

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
        var url = location.href + "/getData?since=" + parseInt(since);
        var json = await fetch(url, { signal: AbortSignal.timeout(4000) })
            .then(res => res.json());
        if (json != null) updateData(json);
        lastUpdateTime = Date.now();
        backoffDelay = 0;
    } catch(err) { 
        if (err.name === "TimeoutError") {
            console.log("Polling Timeout");
            backoffDelay = 5000;
        } else {
            // A network error, or some other problem.
            console.log(`Polling Error: type: ${err.name}, message: ${err.message}`);
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
        .filter(c => c.indexOf("EM_") >=0);

    if (theData.channels.length == 0 && newChannels.length > 0) {
        newChannels.forEach(c => {
          theData.channels.push({
            active: true, 
            dataName: c,
            displayName: c.replace("EM_", "")
          });
        });
    }

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
            const handle = await window.showSaveFilePicker({ 
                types: [
                    {description: "CSV", accept: { "text/csv": [".csv"] }}], 
                excludeAcceptAllOption: false,
                //suggestedName: "",
                startIn: 'downloads'});

            const newName = handle.name;
            const writable = await handle.createWritable();  // not firefox/safari
            if (handle.name.endsWith(".csv")) {
                await writable.write(assembleCSV());
            }    

            // Close the file and write the contents to disk.
            await writable.close();
        } else {
            console.log("opening new window");
            let encoded = encodeURIComponent(assembleCSV()); 
            var dataStr = "data:text/csv;charset=utf-8," + encoded;

            var dlAnchorElem = document.getElementById('downloadAnchorElem');
            dlAnchorElem.setAttribute("href", dataStr);
            dlAnchorElem.setAttribute("download", "rootBotData.csv");
            dlAnchorElem.click();
            //let a = document.createElement(`a`);
            //a.target = `_blank`;
            //a.href = `data:text/csv;charset=utf-8,${encoded}`;
            //a.style.display = `none`;
            //document.body.appendChild(a); // We need to do this,
            //a.click();                    // so that we can do this,
            //document.body.removeChild(a); // after which we do this.
            //var w = window.open("about:blank", "", "_blank")
            //w.document.write("<pre>" + assembleCSV() + "</pre>");
        }
});

function assembleCSV() {
   var csvHdr = 'YYYY-MM-DD,HH:MM:SS.F,Longitude,Latitude,Elevation,Speed,Track,Quality,EM PRP0,EM PRP1,EM PRP2,EM HCP0,EM HCP1,EM HCP2,EM PRPI0,EM PRPI1,EM PRPI2,EM HCPI0,EM HCPI1,EM HCPI2,EM Volts,EM Temperature,EM Pitch,EM Roll,Operator=Rootbot';
   var features = theData.features.features;
   var csvBody = features
       .filter(x => x.properties.recorded) 
       .map(f => {
            var p = f.properties;
            var line = [p.timestamp, p.X, p.Y, p.Z, p.Speed, p.Track, p.Quality].join(",") + "," +
                       [p.EM_PRP0, p.EM_PRP1, p.EM_PRP2, p.EM_HCP0, p.EM_HCP1, p.EM_HCP2,
                        p.EM_PRPI0, p.EM_PRPI1, p.EM_PRPI2, p.EM_HCPI0, p.EM_HCPI1, p.EM_HCPI2,
                        p.EM_Volts, p.EM_Temperature, p.EM_Pitch, p.EM_Roll].join(",");
            return(line);
         })
       .join("\n");

   return(csvHdr + "\n" + csvBody);
}

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
    sLbl.innerText = "Status: " + (status.status == "Running" ? "Recording EM data" : "Idle");

    // roll indicator/warning
    try {
        var features = theData.features.features;
        if (features.length > 0) {
            var lastf = features[features.length - 1];
            if (Math.abs(lastf.properties.EM_Roll) > 10) { // will throw if no data
                sLbl.innerText += " - Roll = " + lastf.properties.EM_Roll;
                var old = sLbl.style.backgroundColor;
                if (old != "#FF0000") {
                    sLbl.style.backgroundColor = "#FF0000";
                }
            } else {
                if (sLbl.style.backgroundColor != "") {
                    sLbl.style.backgroundColor = "";
                }
            }
        }
    } catch (e) {
        console.log(e);
    }
}, 1000);

// Manually start/stop the recorder. Eventually, the polling loop will catch up
// fixme - should have a guard for repeated clicks
document.querySelector('#startStop')
   .addEventListener('click', async (event) => { 
      if(event.target.innerText == "Stop") {
           var url = location.href + "/setStatus?status=Idle"
           fetch(url, { signal: AbortSignal.timeout(1000) });
      } else if(event.target.innerText == "Start") {
           var url = location.href + "/setStatus?status=Running"
           fetch(url, { signal: AbortSignal.timeout(1000) });
      }
   });

let dialog = document.querySelector("#dialog");
document.querySelector("#close-button")
    .addEventListener("click", async () => {
        var url = location.href + "/shutDown"; // fixme add a password to this
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


function drawerToggled (e) {
    if (e.target.id == "channelDrawer") {
        if (e.newState == "open") {
            var w = drawer.querySelectorAll(".chSel");
            w.forEach(b => {
                var chan = theData.channels.find(c => c.displayName == b.innerText);
                if (chan) { b.toggled = chan.active; }

            })
        } else if (e.newState == "closed") {
            var w = drawer.querySelectorAll(".chSel");
            w.forEach(b => {
                var chan = theData.channels.find(c => c.displayName == b.innerText);
                if (chan) { chan.active = b.toggled; }
            })
        }
    }
}

let drawer = document.querySelector("#channelDrawer");
drawer.addEventListener("toggle", (e) => drawerToggled(e) );

let closeButton = document.querySelector("#channel-close-button");
closeButton.addEventListener("click", () => drawer.close());
