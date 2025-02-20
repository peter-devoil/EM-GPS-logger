(function (global, factory) {
        typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
               typeof define === 'function' && define.amd ? define(['exports'], factory) :
                      (factory((global.myMap = global.myMap || {})));
 }(this, (function (exports) {
       'use strict';
        var width = -1;
        var height = -1;
        var version = "0.0.1";
        var plotData = null;
        var mapMode = "panMode";

       // get the data
       function loadEMData( emData ) {
              emData.selected = new Array(emData.features.length).fill(true);
              for (var i = 0; i <emData.features.length; i++) {
                     emData.features[i].properties._featureId = i;
              }
       }

       function loadPlotData( plotData ) {
              //plotData = _plotData;
       }

       function drawData(element, emData, plotData) {
              element.replaceChildren();

              width = 400;//element.offsetWidth;
              height = 400;//element.offsetHeight;

              // Get the bounding box of the paths (in pixels!) and calculate a
              // scale factor based on the size of the bounding box and the map
              // size.
              var p1 = d3.geoPath().projection(d3.geoMercator().scale(1));
              var bbox_path1 = null;
              if (plotData != null) {
                     bbox_path1 = p1.bounds(plotData);
              }
              var bbox_path2 = null;
              if (emData != null) {
                     bbox_path2 = p1.bounds(emData);
              } 
              if (bbox_path1 == null && bbox_path2 == null) { return; }
              var bbox_path = bbox_path1;
              if (bbox_path == null && bbox_path2 != null) {
                     bbox_path = bbox_path2;
              } else if (bbox_path != null && bbox_path2 != null) {
                     bbox_path = [[Math.min(bbox_path[0][0], bbox_path2[0][0], bbox_path[1][0], bbox_path2[1][0]),
                                   Math.min(bbox_path[0][1], bbox_path2[0][1], bbox_path[1][1], bbox_path2[1][1])],
                                  [Math.max(bbox_path[0][0], bbox_path2[0][0], bbox_path[1][0], bbox_path2[1][0]),
                                   Math.max(bbox_path[0][1], bbox_path2[0][1], bbox_path[1][1], bbox_path2[1][1])]]
              }

              var scale = 0.95 / Math.max(
                     (bbox_path[1][0] - bbox_path[0][0]) / width,
                     (bbox_path[1][1] - bbox_path[0][1]) / height
              );

              // Get the bounding box of the features (in map units!) and use it
              // to calculate the center of the features.
              var bbox_feature1 = null;
              if (plotData != null) {
                     bbox_feature1 = d3.geoBounds(plotData);
              }
              var bbox_feature2 = null;
              if (emData != null) {
                     bbox_feature2 = d3.geoBounds(emData);
              } 
              if (bbox_feature1 == null && bbox_feature2 == null) { return; }
              var bbox_feature = bbox_feature1;
              if (bbox_feature == null && bbox_feature2 != null) {
                     bbox_feature = bbox_feature2;
              } else if (bbox_feature != null && bbox_feature2 != null) {
                     bbox_feature = [[Math.min(bbox_feature[0][0], bbox_feature2[0][0], bbox_feature[1][0], bbox_feature2[1][0]),
                                      Math.min(bbox_feature[0][1], bbox_feature2[0][1], bbox_feature[1][1], bbox_feature2[1][1])],
                                     [Math.max(bbox_feature[0][0], bbox_feature2[0][0], bbox_feature[1][0], bbox_feature2[1][0]),
                                      Math.max(bbox_feature[0][1], bbox_feature2[0][1], bbox_feature[1][1], bbox_feature2[1][1])]]
              }

              var center = [(bbox_feature[1][0] + bbox_feature[0][0]) / 2,
              (bbox_feature[1][1] + bbox_feature[0][1]) / 2];
              
              var projection = d3.geoMercator().scale(scale)
                            .center(center)
                            .translate([width / 2, height / 2]);
              var path = d3.geoPath(projection);

              var svg = d3.select(element)
                     .append('svg')
                     .attr("preserveAspectRatio", "xMidYMid meet") 
                     .attr("viewBox", "0 0 " + width + " " + height)
                     .classed("svg-content-responsive", true);

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
                            .style("fill", "#69b3a2")
                            .on("click", (e, d) => clickEvent(e, d));
              }


              function handleZoom(e) { svg.selectAll('g').attr('transform', e.transform);}
              svg.call(d3.zoom().filter(() => mapMode == "panMode").on('zoom', handleZoom)); 

              function clickEvent(e, data) {
                     var t = e.target;
                     var featureIdx = data.properties._featureId;
                     switch (mapMode) {
                            case "yesMode":
                                  emData.selected[featureIdx] = true;
                                  t.style.fill = "#69b3a2"
                                  break;
                            case "noMode":
                                  emData.selected[featureIdx] = false;
                                  t.style.fill = "purple"
                                  break;
                     }             
              }
       }

              function recolourData(element, emData) {
                     if (emData != null) {
                            d3.selectAll("circle")
                                   .style("fill", (d) => {
                                          if (emData.selected[d.properties._featureId] == false)
                                                 return ("purple");
                                          if (d.properties[[emData.selectedChannel]] < emData.lowerBounds[emData.selectedChannel])
                                                 return ("blue");
                                          if (d.properties[[emData.selectedChannel]] > emData.upperBounds[emData.selectedChannel])
                                                 return ("red");
                                          return ("#69b3a2");
                                   });
                     }
              }


        function setMapMode(element, mode) {
               mapMode = mode;
               //var svg = d3.select(element)
               switch (mode) {
                      case "panMode":

                             break;
                      case "yesMode":

                             break;
                      case "noMode":

                             break;
               }
        }

       exports.version = version;
       exports.recolourData = recolourData;
       exports.loadEMData = loadEMData;
       exports.loadPlotData = loadPlotData;
       exports.drawData = drawData;
       exports.setMapMode = setMapMode;
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