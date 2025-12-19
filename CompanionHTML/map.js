(function (global, factory) {
        typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
               typeof define === 'function' && define.amd ? define(['exports'], factory) :
                      (factory((global.myMap = global.myMap || {})));
 }(this, (function (exports) {
       'use strict';
       var width = -1;
       var height = -1;
       var version = "0.0.1";
       var lastId = -1;
       var bbox = [[0,0],[0,0]];
       //var margin = { top: 0, right: 0, bottom: 0, left: 0 };
       var margin = { top: 10, right: 10, bottom: 30, left: 40 };

       var svg = null;

       function initData(element) {
             width = element.clientWidth;
             height = element.clientHeight;
             if (width <= 0 || height <= 0) { console.log("zero WH"); return; }

             element.replaceChildren();

             svg = d3.select(element)
               .append('svg')
               .classed("svg-content", true)
               .attr("preserveAspectRatio", "xMidYMid meet") 
               .attr("viewBox", [0, 0, width, height])
               //.attr("viewBox", margin.top + " " + margin.left + " " + width + " " + height)
               .attr("transform", "translate(" + margin.left + "," + margin.top + ")");
       }

       function bbox_EQ(a, b) {
              return (isEqCT(a[0,0], b[0,0]) &&
                      isEqCT(a[1,0], b[1,0]) &&
                      isEqCT(a[0,1], b[0,1]) &&
                      isEqCT(a[1,0], b[1,0]));
       }
       function addData(element, theData) {

               if (theData.features == null) { return; }

               // Get the bounding box of the paths (in pixels!) and calculate a
               // scale factor based on the size of the bounding box and the map
               // size.
               var p1 = d3.geoPath().projection(d3.geoMercator().scale(1));
               var bbox_path = p1.bounds(theData.features);
               var newExtents = false;
               if (!bbox_EQ(bbox, bbox_path)) {
                     bbox = bbox_path;
                     newExtents = true;
               }

               var scale = 0.95 / Math.max(
                      (bbox_path[1][0] - bbox_path[0][0]) / width,
                      (bbox_path[1][1] - bbox_path[0][1]) / height
               );

               if (! isFinite(scale)) { return; }


               // Get the bounding box of the features (in map units!) and use it
               // to calculate the center of the features.
               var bbox_features = d3.geoBounds(theData.features);

               var center = [(bbox_features[1][0] + bbox_features[0][0]) / 2,
                             (bbox_features[1][1] + bbox_features[0][1]) / 2];

               var projection = d3.geoMercator().scale(scale)
                      .center(center)
                      .translate([width / 2, height / 2]);

               var path = d3.geoPath(projection);

               var newDataIndex = theData.features.features.findIndex(x => x.properties.id > lastId);
               lastId = theData.features.features[theData.features.features.length - 1].properties.id;

               // Add the EM points
               var newFeatures;
               if (newExtents) {
                     // Wipe everything
                     svg.selectAll("g").remove();
                     newFeatures = theData.features;
               } else {
                     // Just the bits from today
                     var n = newDataIndex; //fixme - this isnt being called?
                     newFeatures = theData.features.slice(n);
               }

               svg.append("g")
                      .selectAll("emPath")
                      .data(newFeatures.features)
                      .enter()
                      .append("circle")
                      .attr("transform", function (d) { 
                            return "translate(" + path.centroid(d.geometry) + ")"; 
                       })
                      .attr("r", 2)
                      .style("fill", "#69b3a2");

             var currFeatures = [ theData.features.features[theData.features.features.length - 1] ];
             svg.append("g")
                      .selectAll("currEMPath")
                      .data(currFeatures)
                      .enter()
                      .append("circle")
                      .attr("transform", function (d) { 
                            return "translate(" + path.centroid(d.geometry) + ")"; 
                       })
                      .attr("r", 4)
                      .style("fill", "#ff0000");
        }
       
       exports.version = version;
       exports.initData = initData;
       exports.addData = addData;
       Object.defineProperty(exports, '__esModule', { value: true });
})));

/* Notes
reading geotiff 

https://observablehq.com/d/719a22e6fa68dccb
img = (await FileAttachment('wp.tif')).arrayBuffer()
  .then(t => geotiff.fromArrayBuffer(t))
  .then(t => t.getImage())

https://gist.github.com/rveciana/263b324083ece278e966686d7dba700f


 */