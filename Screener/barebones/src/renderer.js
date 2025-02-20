'use strict';


// const styles = document.createElement('style');
// styles.innerText = `@import url(https://unpkg.com/spectre.css/dist/spectre.min.css);.empty{display:flex;flex-direction:column;justify-content:center;height:100vh;position:relative}.footer{bottom:0;font-size:13px;left:50%;opacity:.9;position:absolute;transform:translateX(-50%);width:100%}`;

// const vueScript = document.createElement('script');
// vueScript.setAttribute('type', 'text/javascript'),
//     vueScript.setAttribute('src', 'https://unpkg.com/vue'),
//     vueScript.onload = init,
//     document.head.appendChild(vueScript),
//     document.head.appendChild(styles);
// function init() {
//     Vue.config.devtools = false,
//     Vue.config.productionTip = false,
//     new Vue({
//         data: {
//             versions: {
//                 electron: process.versions.electron,
//                 electronWebpack: require('electron-webpack/package.json').version
//             }
//         },
//         methods: { open(b) { require('electron').shell.openExternal(b) } },
//         template: `<div><div class=empty><p class="empty-title h5">Welcome to your new project!<p class=empty-subtitle>Get qwdqwd now and take advantage of the great documentation at hand.<div class=empty-action><button @click="open('https://webpack.electron.build')"class="btn btn-primary">Documentation</button> <button @click="open('https://electron.atom.io/docs/')"class="btn btn-primary">Electron</button><br><ul class=breadcrumb><li class=breadcrumb-item>electron-webpack v{{ versions.electronWebpack }}</li><li class=breadcrumb-item>electron v{{ versions.electron }}</li></ul></div><p class=footer>This intitial landing page can be easily removed from <code>src/renderer/index.js</code>.</p></div></div>`
//     }).$mount('#app')
// }


// This file is required by the index.html file and will
// be executed in the renderer process for that window.
// All of the Node.js APIs are available in this process.


var histElement = document.querySelector('.histogram');
var mapElement = document.querySelector('.map');
var msgElement = document.querySelector(".messagebox")
var split = Split(['#split-0', '#split-1'] /*, {onDragEnd: () => myHist.setupHist(histElement)}*/);

//var selectedChannel = "Undefined";

var emData = null;
var plotData = null;

document.querySelector('#channelSelector')
    .addEventListener('change', function () { 
        console.log("Change channelSelector: " + this.value);
        emData.selectedChannel = this.value;
        myHist.drawData(histElement, msgElement, emData);
        myMap.drawData(mapElement, emData, plotData);
    }, false);

// Get the EM data from a file. Can be either csv or shapefile
document.querySelector('#open_em_data')
    .addEventListener('click', async() => { 
        //fixme add file types to options
    const handles = await window.showOpenFilePicker({multiple: true, startIn: 'downloads'});
    if (handles.length == 1) {
        const file = await handles[0].getFile();
        var ext = file.name.split(".").pop();
        //fixme test if csv extension
        const data = await file.text();
        csv2geojson.csv2geojson(data, { latfield: 'Latitude',lonfield: 'Longitude'}, 
            function(err, data) {
                emData = data;
                // err has any parsing errors fixme
        });
    } else if (handles.length > 1) {
        const shpBundle = {};
        for(const h of handles) {
            var file = await h.getFile();
            if (file.name.endsWith(".shp")) {
                shpBundle.shp = await file.arrayBuffer();
            } else if (file.name.endsWith(".dbf")) {
                shpBundle.dbf = await file.arrayBuffer();
            } else if (file.name.endsWith(".prj")) {
                shpBundle.prj = await file.arrayBuffer();
            } else if (file.name.endsWith(".cpg")) {
                shpBundle.cpg = await file.arrayBuffer();
            }
        }
        
        emData = await shp(shpBundle);
    } else {
        //fixme user cancelled
        return;
    }

    // Change the combobox for new channel names
    var combo = document.getElementById("channelSelectorMenu");
    combo.replaceChildren();

    var channels = Object.getOwnPropertyNames(emData.features[0].properties).
        filter(c => c.indexOf("PRP") >=0 || c.indexOf("HCP") >=0);

    channels.forEach(c => {
        combo.innerHTML += "<x-menuitem value=\"" + c + "\">" +
            "<x-label>" + c + "</x-label>" +
            "</x-menuitem>";
    });

    combo.selectedIndex = 0;
    combo.focusFirstMenuItem();
    emData.selectedChannel = channels[0];
    var selector = document.getElementById("channelSelector");
    selector.value = channels[0];

    myHist.loadEMData( emData );
    myHist.drawData( histElement, msgElement, emData )
    
    myMap.loadEMData( emData );
    myMap.drawData( mapElement, emData, plotData );
    myMap.recolourData( mapElement , emData);
});

// Get the plot outline data from a file. Usually .shp 
document.querySelector('#open_plot_data')
    .addEventListener('click', async() => { 
    const shpBundle = {};
    const handles = await window.showOpenFilePicker({multiple: true, startIn: 'downloads'});
    for(const h of handles) {
        file = await h.getFile();
        if (file.name.endsWith(".shp")) {
            shpBundle.shp = await file.arrayBuffer();
        } else if (file.name.endsWith(".dbf")) {
            shpBundle.dbf = await file.arrayBuffer();
        } else if (file.name.endsWith(".prj")) {
            shpBundle.prj = await file.arrayBuffer();
        } else if (file.name.endsWith(".cpg")) {
            shpBundle.cpg = await file.arrayBuffer();
        }
    }
    
    plotData = await shp(shpBundle);
    myMap.loadPlotData( plotData );
    myMap.drawData(mapElement, emData, plotData);
    myMap.recolourData(mapElement, emData);
});


// Get the EM data from a file. Can be either csv or shapefile
document.querySelector('#save_data')
    .addEventListener('click', async () => {
        const handle = await window.showSaveFilePicker({
            types: [
                {description: "Shapefile (zipped)", accept: { "application/zip": [".zip"] }}, 
                {description: "CSV", accept: { "text/csv": [".csv"] }}], 
            excludeAcceptAllOption: false,
            //suggestedName: "",
            startIn: 'downloads'});

        var channels = Object.getOwnPropertyNames(emData.features[0].properties)
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
myHist.setRecolour (function () { 
    myMap.recolourData( mapElement, emData); 
});

// Listen for change in the entry boxes and update chart bars
document.querySelector('#lowBoundInput')
    .addEventListener('change', async(e) => { 
        emData.lowerBounds[emData.selectedChannel] = e.target.value;
        myHist.updateBounds( histElement, msgElement, emData )
    });

document.querySelector('#highBoundInput')
    .addEventListener('change', async(e) => { 
        emData.upperBounds[emData.selectedChannel] = e.target.value;
        myHist.updateBounds( histElement, msgElement, emData )
    });


document.querySelector('#mapMode')
    .addEventListener('toggle', async(e) => { 
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
        myMap.setMapMode(mapElement, sel.id);
    });
    