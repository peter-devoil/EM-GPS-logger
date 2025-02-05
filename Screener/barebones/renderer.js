// This file is required by the index.html file and will
// be executed in the renderer process for that window.
// All of the Node.js APIs are available in this process.


var histElement = document.querySelector('.histogram');
var mapElement = document.querySelector('.map');
var msgElement = document.querySelector(".messagebox")
var split = Split(['#split-0', '#split-1'] /*, {onDragEnd: () => myHist.setupHist(histElement)}*/);

var selectedChannel = "Undefined";

var emData = null;
var plotData = null;

document.querySelector('#channelSelector')
    .addEventListener('change', function () { 
        console.log("Change channelSelector: " + this.value);
        selectedChannel = this.value;
        myHist.drawData(histElement, msgElement, selectedChannel);
        myMap.drawData(mapElement, selectedChannel);
    }, false);

// Get the EM data from a file. Can be either csv or shapefile
document.querySelector('#open_em_data')
    .addEventListener('click', async() => { 
    const handles = await window.showOpenFilePicker({multiple: true, startIn: 'downloads'});
    if (handles.length == 1) {
        const file = await handles[0].getFile();
        var ext = file.name.split(".").pop();
        //fixme test if csv extension
        const data = await file.text();
        emData = csv2geojson.csv2geojson(data, { latfield: 'Latitude',lonfield: 'Longitude'}, 
            function(err, data) {
            // err has any parsing errors fixme
        });
    } else if (handles.length > 1) {
        const shpBundle = {};
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
    var selector = document.getElementById("channelSelector");
    selector.value = selectedChannel = channels[0];

    myHist.loadEMData( emData );
    myHist.drawData( histElement, msgElement, selectedChannel )
    
    myMap.loadEMData( emData );
    myMap.drawData( mapElement, selectedChannel );
    myMap.recolourData( mapElement, selectedChannel );
});

// Get the plot outline data from a file
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
    myMap.drawData(mapElement, selectedChannel);
    myMap.recolourData(mapElement, selectedChannel);
});

myHist.setRecolour (function () { 
    myMap.recolourData( mapElement, selectedChannel ); 
});
