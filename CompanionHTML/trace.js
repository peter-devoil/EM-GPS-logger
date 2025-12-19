(function (global, factory) {
       typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
              typeof define === 'function' && define.amd ? define(['exports'], factory) :
                     (factory((global.myTrace = global.myTrace || {})));
}(this, (function (exports) {
       'use strict';

       var version = "0.0.1";

       // set the dimensions and margins of the graph
       var svg;
       var margin = { top: 10, right: 10, bottom: 30, left: 40 };
       var width = -1;
       var height = -1;

       // get the data
       function initData(element) {
              width =  element.clientWidth; // 500 - margin.left - margin.right;
              height = element.clientHeight; //500 - margin.top - margin.bottom;

              if (width <= 0 || height <= 0) { console.log("zero WH"); return; }

              element.replaceChildren();
              svg = d3.select(element)
                     .append('svg')
                     .classed("svg-content", true)
                     .attr("preserveAspectRatio", "xMidYMid meet")
                     .attr("viewBox", [0, 0, width, height]);
                     //.attr("viewBox", margin.top + " " + margin.left + " " + width + " " + height)
                     //.attr("transform", "translate(" + margin.left + "," + margin.top + ")");
              
       }

       function checkExtents(theData, from) {
              var changed = false;
              theData.channels.forEach(c => {
                     var lower = 1000;
                     var upper = -1000;
                     theData.features.features.slice(from).forEach(d => {
                            lower = Math.min(lower, d.properties[c.dataName]);
                            upper = Math.max(upper, d.properties[c.dataName]);
                     });
                     if (lower < theData.lowerBounds[c.dataName]) {
                            changed = true;
                            theData.lowerBounds[c.dataName] = lower;
                     }
                     if (upper > theData.upperBounds[c.dataName]) {
                            changed = true;
                            theData.upperBounds[c.dataName] = upper;
                     }
                     // Alternatives: this is the entire dataset - both on the ground and in the air,
                     // so it may be better to calculate bounds over some recent time

                     /*            const sum = arr => arr.reduce((partialSum, a) => partialSum + a, 0);
                                   const mean = arr => sum(arr) / arr.length;
                                   const variance = arr => {
                                          const m = mean(arr);
                                          return (sum(arr.map(v => (v - m) ** 2)) / arr.length);
                                      };
                                   const sd = arr => Math.sqrt(variance(arr));
                                   
                                   var m = mean(thisChan);
                                   var stdd = sd(thisChan);
                     
                                   theData.lowerBounds[c] = m - 2 * stdd;
                                   theData.upperBounds[c] = m + 2 * stdd;
                      */
              });
              return (changed);
       }


       // keep these around for later..
       var tWindow = 60; //seconds
       let emAxes = [];

       function addData(element, theData) {
              var myData = [];
              var features = theData.features.features
              var tLast = features[features.length - 1].properties.time;
              for (var i = features.length - 1; 
                     i > 0 && tLast - features[i].properties.time <  tWindow * 1000;
                     i--) {
                     myData.push(features[i].properties);
              }

              myData = myData.reverse();
              var tEnd = myData[myData.length-1].time;
              var tBegin = myData[0].time;

              var emBoundsChanged = checkExtents(theData, i);

              var tScale = d3.scaleTime()
                     .domain([tBegin, tEnd])
                     .range([margin.left, width - margin.right]);

              svg.select("#" + "tAxis").remove();
              svg.append("g")
                     .attr("id", "tAxis")
                     .style("font", "10px roboto")
                     .attr("transform", "translate(" + 0 + "," + (height - margin.bottom) + ")")
                     .call(d3.axisBottom(tScale).ticks(6));

              var activeChannels = theData.channels
                     .filter(c => c.active );

              // Create the channel axes 
              var channelHeight = Math.max(0, (height - margin.top - margin.bottom ) / activeChannels.length);
              if (emAxes.length == 0 || emBoundsChanged) {
                     // Y axis: minor axis for each channel
                     emAxes["major"] = d3.scaleBand()
                            .domain(activeChannels.map(c => c.displayName))
                            .range([height - margin.bottom, margin.top]);

                     activeChannels.forEach(c => {
                            emAxes[c.displayName] = d3.scaleLinear()
                                   .domain([theData.lowerBounds[c.dataName], theData.upperBounds[c.dataName]])
                                   .range([0, channelHeight]);
                     });
              }

              svg.select("#" + "emAxis").remove();
              svg.append("line")
                     .attr("id", "emAxis")
                     .attr("y1", margin.top)
                     .attr("y2", height - margin.bottom )
                     .attr("x1", margin.left)
                     .attr("x2", margin.left)
                     .style("stroke", "#000000");

              //console.log("prp1=" + myData.last()["EM_PRP1"]);
              theData.channels.forEach(c => {
                     if (!c.active) {
                            svg.selectAll("#trace" + c.displayName).remove();
                            svg.selectAll("#emlow" + c.displayName).remove();
                            svg.selectAll("#emhigh" + c.displayName).remove();
                            svg.selectAll("#emAxisTic" + c.displayName).remove();
                     }
              });

              activeChannels.forEach(c => {
                     svg.selectAll("#trace" + c.displayName).remove();
                     svg.append("path")
                            .datum(myData)
                            .attr("id", "trace" + c.displayName)
                            .attr("d", d3.line()
                              .y(function(d) {  var y = height - margin.bottom - emAxes["major"](c.displayName) - emAxes[c.displayName](d[c.dataName]); 
                                   return(y); })
                              .x(function(d) {  var xx =  tScale(d.time);  
                                         return(xx); })
                            )
                            .style("stroke", "#69b3a2")
                            .style("fill", "none");
                     svg.selectAll("#emlow" + c.displayName).remove();
                     svg.append("text")
                            .attr("id", "emlow" + c.displayName)
                            .attr("y", height - margin.bottom - emAxes["major"](c.displayName) )
                            .attr("x", width - margin.right)
                            .attr("dy", -2)
                            .attr("text-anchor", "end")
                            .text(theData.lowerBounds[c.dataName])
                            .style("font", "10px roboto");
                     svg.selectAll("#emhigh" + c.displayName).remove();
                     svg.append("text")
                            .attr("id", "emhigh" + c.displayName)
                            .attr("y", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight)
                            .attr("x", width - margin.right)
                            .attr("dy", 12)
                            .attr("text-anchor", "end")
                            .text(theData.upperBounds[c.dataName])
                            .style("font", "10px roboto");
                     svg.append("line")
                            .attr("id", "emhigh" + c.displayName)
                            .attr("y1", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight)
                            .attr("y2", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight)
                            .attr("x1", margin.left)
                            .attr("x2", width - margin.right)
                            .style("stroke", "#aaaaaa")
                            .style("fill", "none");
                     svg.selectAll("#emAxisTic" + c.displayName).remove();
                     svg.append("line")
                            .attr("id", "emAxisTic" + c.displayName)
                            .attr("y1", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight/2)
                            .attr("y2", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight/2)
                            .attr("x1", margin.left)
                            .attr("x2", margin.left-3)
                            .style("stroke", "#000000");
                     svg.append("text")
                            .attr("id", "emAxisTic" + c.displayName)
                            .attr("y", height - margin.bottom - emAxes["major"](c.displayName) - channelHeight/2)
                            .attr("x", margin.left )
                            .attr("dx", -4)
                            .attr("dy", 5)
                            .attr("text-anchor", "end")
                            .text(c.displayName)
                            .style("font", "10px roboto");
       
              });
       }


       exports.version = version;
       exports.initData = initData;
       exports.addData = addData;

       Object.defineProperty(exports, '__esModule', { value: true });

})));

