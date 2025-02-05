(function (global, factory) {
        typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
               typeof define === 'function' && define.amd ? define(['exports'], factory) :
                      (factory((global.myMap = global.myMap || {})));
 }(this, (function (exports) {
       'use strict';
        var width = -1;
        var height = -1;
        var version = "0.0.1";
        var emData = null;
        var plotData = null;

       // get the data
       function loadEMData( _emData ) {
              emData = _emData;
       }

       function loadPlotData( _plotData ) {
              plotData = _plotData;
       }

       function drawData(element, selectedChannel) {
              element.replaceChildren();

              width = element.offsetWidth;
              height = element.offsetHeight;

              // Get the bounding box of the paths (in pixels!) and calculate a
              // scale factor based on the size of the bounding box and the map
              // size.
              var p1 = d3.geoPath().projection(d3.geoMercator().scale(1));
              var bbox_path = [];
              if (plotData != null) {
                   bbox_path = p1.bounds(plotData); // fixme include em data too
              } 

              if (bbox_path.length == 0) { return; }
              var scale = 0.95 / Math.max(
                     (bbox_path[1][0] - bbox_path[0][0]) / width,
                     (bbox_path[1][1] - bbox_path[0][1]) / height
              );

              // Get the bounding box of the features (in map units!) and use it
              // to calculate the center of the features.
              var bbox_feature = d3.geoBounds(plotData);
              var center = [(bbox_feature[1][0] + bbox_feature[0][0]) / 2,
                            (bbox_feature[1][1] + bbox_feature[0][1]) / 2];

              var projection = d3.geoMercator().scale(scale)
                            .center(center)
                            .translate([width / 2, height / 2]);

              var path = d3.geoPath(projection);

              var svg = d3.select(element)
                     .append('svg')
                     .attr("preserveAspectRatio", "xMinYMin meet")
                     .attr("viewBox", "0 0 400 300")
                     .classed("svg-content-responsive", true);
                     //.attr("width", width )
                     //.attr("height", height )
              if (plotData != null) {
                     svg.append("g")
                            .selectAll("plotPath")
                            .data(plotData.features)
                            .enter()
                            .append("path")
                            .attr("fill", "grey")
                            .attr("d", path)
                            .style("stroke", "grey");
              }
              // Add the EM points
              if (emData != null) {
                     svg.append("g")
                            .selectAll("emPath")
                            .data(emData.features)
                            .enter()
                            .append("circle")
                            .attr("transform", function (d) { return "translate(" + path.centroid(d) + ")"; })
                            .attr("r", 2)
                            .style("fill", "purple");
              }


              function handleZoom(e) { svg.attr('transform', e.transform);}
              svg.call(d3.zoom().on('zoom', handleZoom)); 
       }

       function recolourData(element, selectedChannel) {
              if (emData != null) {
                     d3.selectAll("circle")
                            .style("fill", (d) => {
                                   if (d.properties[[selectedChannel]] < emData.lowerBounds[selectedChannel])
                                          return("blue");
                                   if (d.properties[[selectedChannel]] > emData.upperBounds[selectedChannel])
                                          return("red");
                                   return("purple");});
              }
       }       

       exports.version = version;
       exports.recolourData = recolourData;
       exports.loadEMData = loadEMData;
       exports.loadPlotData = loadPlotData;
       exports.drawData = drawData;
       Object.defineProperty(exports, '__esModule', { value: true });
})));

