'use strict';

// This file is required by the index.html file and will
// be executed in the renderer process for that window.
// All of the Node.js APIs are available in this process.

var traceElement = document.querySelector('#trace');
var mapElement = document.querySelector('#map');
var msgElement = document.querySelector("#messages")
var split = Split(['#split-0', '#split-1'] /*, {onDragEnd: () => myHist.setupHist(histElement)}*/);

var theData = {features: {features : [], type : "FeatureCollection"}, data: [], lowerBounds: [], upperBounds: []};

var updateInterval = 1000; // milliseconds
var lastUpdateTime = Date.now();
var updateTimer = null; // timer ID that will update window contents / colour
var statusTimer = null; // "     "   for monitoring companion status

var pollingInterval = setTimeout(pollForMore, updateInterval);

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

async function pollForMore() {
    var since = 0
    try {
        if (theData.data.length > 0) {
            since = theData.data.last().id;
        }
        var url = location.href + "/getData?since=" + parseInt(since);
        var json = await fetch(url)
            .then(res => res.json());
        if (json != null) updateData(json);
        lastUpdateTime = Date.now();
    } catch(err) { 
        console.log(err);
    }
    pollingInterval = setTimeout(pollForMore, updateInterval);
}

function stopInterval() {
    clearTimeout(pollingInterval);
}

function updateData (json) {
    var lastid = 0;
    if (theData.data.length > 0) {
        var x= theData.data.last();
        lastid = x.id;
    }

    json.forEach(r => {
        if (r.id > lastid) { 
            r.time = moment(r.timestamp, "yyyy-MM-dd,HH:mm:ss");
            Object.keys(r).forEach(k => {
                if (k.indexOf("PRP") >=0 || k.indexOf("HCP") >= 0) {
                    r[k] = parseFloat(r[k]);
                }
            });
            theData.data.push(r); 
            var f = {"geometry" : {"coordinates": [parseFloat(r["X"]), parseFloat(r["Y"])], "type": "Point"},
                 "properties" : r};
            theData.features.features.push(f);
        }
    });

    //csv2geojson.csv2geojson(theData.data.slice(theData.features.length, theData.data.length), { latfield: 'Y',lonfield: 'X'}, 
    //csv2geojson.csv2geojson(theData.data, { latfield: 'Y',lonfield: 'X'}, 
    //        function(err, data) { 
    //            theData.features = data
    //});


    theData.channels = Object.keys(theData.data[0])
       .filter(c => c.indexOf("PRP") >=0 || c.indexOf("HCP") >=0)
       .map(s => s.replace("EM_", ""));

    theData.channels.forEach( c=> {
        if (typeof theData.lowerBounds[c] == "undefined") {
            theData.lowerBounds[c] = 1000;
        }
        if (typeof theData.upperBounds[c] == "undefined") {
            theData.upperBounds[c] = -1000;
        }
    });
    
    myTrace.addData( traceElement, theData );
    myMap.addData( mapElement, theData );
}

// Start or stop the logger manually
document.querySelector('#startStop')
    .addEventListener('toggle', async (e) => { 
        var w = e.target;
        var sel = e.detail;
        w.childNodes.forEach(x => {
            if (typeof(x.id) != "undefined") {
                if (sel.id != x.id) {
                    x.toggled = false;
                 } else {
                    x.toggled = true;
                 }
            } 
        });
        //myMap.setMapMode(mapElement, sel.id);
    });

// Save the EM data to a file. Can be either csv or shapefile
document.querySelector('#save_data')
    .addEventListener('click', async () => {
        const handle = await window.showSaveFilePicker({ // fixme - if this fails, open a text/plain window for the user to save
            types: [
                {description: "Shapefile (zipped)", accept: { "application/zip": [".zip"] }}, 
                {description: "CSV", accept: { "text/csv": [".csv"] }}], 
            excludeAcceptAllOption: false,
            //suggestedName: "",
            startIn: 'downloads'});

        var channels = emData.features.keys
           .filter(c => c.indexOf("PRP") >=0 || c.indexOf("HCP") >=0);

        channels.forEach(c => {
            for (var i = 0; i < emData.features.length; i++) {
                var x = emData.features[i].properties[c];
                var value;
                if (typeof x === 'string' || x instanceof String)
                    value = parseFloat(x);
                else
                    value = x;
                if (emData.selected[i] == true &&
                    value >= emData.lowerBounds[c] &&
                    value <= emData.upperBounds[c]) {
                    /*emData.selected[i] = true; */
                } else {
                    emData.selected[i] = false; //fixme: this is modifying the original, should be a copy
                }
            }
        });

        var dataToWrite = new Object();
        dataToWrite.features = [];
        dataToWrite.type = emData.type;
        for (var i = 0; i < emData.features.length; i++) {
            if (emData.selected[i] == true) {
                dataToWrite.features.push(emData.features[i]);
            }
        }

        const newName = handle.name;
        const writable = await handle.createWritable();  // not firefox/safari
        if (handle.name.endsWith(".csv")) {
            var csvHdr = ["Longitude", "Latitude",]
                 .concat(Object.keys(dataToWrite.features[0].properties));
            var csvBody = dataToWrite.features.map(f => 
                Object.values(f.geometry.coordinates).toString()
                   .concat(",")
                   .concat(Object.values(f.properties).toString())).join("\n");
            await writable.write(csvHdr + "\n" + csvBody);
        }    

        // fixme
        // if (handle.name.endsWith(".zip")) {
        //     const zipData = await shpwrite.zip(dataToWrite);
        //     await writable.write(zipData);
        // } else {
        //     const csvData = null; 
        // }

        // Close the file and write the contents to disk.
        await writable.close();
    });

function convertToCSV(arr) {
    const array = [Object.keys(arr[0])].concat(arr)
    return array.map(it => {
        return Object.values(it).toString()
    }).join('\n')
}

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

    // fixme - this should be bundled in with the getData call above
    var url = location.href + "/getStatus"
    var status = await fetch(url).then(res => res.json());

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
    // fixme add roll indicator/warning

}, 1000);

// Manually start/stop the recorder. Eventually, the polling loop will catch up
// fixme - should have a guard for repeated clicks
document.querySelector('#startStop')
   .addEventListener('click', async (event) => { 
      if(event.target.innerText == "Stop") {
           var url = location.href + "/setStatus?status=Idle"
           fetch(url);
      } else if(event.target.innerText == "Start") {
           var url = location.href + "/setStatus?status=Running"
           fetch(url);
      }
   });

let dialog = document.querySelector("#dialog");
document.querySelector("#close-button")
    .addEventListener("click", async () => {
        var url = location.href + "/shutDown"; // fixme add a password to this
        var json = await fetch(url);
        dialog.close();
});

document.querySelector('#powerOff')
   .addEventListener('click', async () => { 
        dialog.showModal(); 
   }
);

