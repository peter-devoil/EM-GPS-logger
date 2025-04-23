(function (global, factory) {
       typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
              typeof define === 'function' && define.amd ? define(['exports'], factory) :
                     (factory((global.myTrace = global.myTrace || {})));
}(this, (function (exports) {
       'use strict';

       var version = "0.0.1";

       // set the dimensions and margins of the graph
       var width = -1;
       var height = -1;
       var svg;

       // get the data
       function initData(element) {
              element.replaceChildren();

              var margin = { top: 10, right: 30, bottom: 30, left: 40 };

              width = /*element.clientWidth*/ 400 - margin.left - margin.right;
              height = /*element.clientHeight*/ 400 - margin.top - margin.bottom;

              if (width <= 0 || height <= 0) { console.log("zero WH"); return; }

              svg = d3.select(element)
                     .append('svg')
                     .classed("svg-content-responsive", true)
                     .attr("preserveAspectRatio", "xMidYMid meet")
                     .attr("viewBox", "0 0 400 400")
                     //.attr("width", width + margin.left + margin.right)
                     .append("g")
                     .attr("viewBox", margin.top + " " + margin.left + " " + width + " " + height)
                     .attr("transform",
                            "translate(" + margin.left + "," + margin.top + ")");
       }

       function checkExtents(theData, from) {
              var changed = false;
              theData.channels.forEach(c => {
                     var lower = 1000;
                     var upper = -1000;
                     theData.data.slice(from).forEach(d => {
                            lower = Math.min(lower, d["EM_" + c]);
                            upper = Math.max(upper, d["EM_" + c]);
                     });
                     if (lower < theData.lowerBounds[c]) {
                            changed = true;
                            theData.lowerBounds[c] = lower;
                     }
                     if (upper > theData.upperBounds[c]) {
                            changed = true;
                            theData.upperBounds[c] = upper;
                     }

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
       let xAxes = [];

       function addData(element, theData) {
              var myData = [];
              var tLast = theData.data[theData.data.length - 1].time;
              for (var i = theData.data.length - 1; 
                     i > 0 && tLast - theData.data[i].time <  tWindow * 1000;
                     i--) {
                     myData.push(theData.data[i]);
              }
              myData = myData.reverse();
              var tEnd = myData[myData.length-1].time;
              var tBegin = myData[0].time;

              var xBoundsChanged = checkExtents(theData, i);

              var y = d3.scaleTime()
                     .domain([tBegin, tEnd])
                     .range([0, height]);

              svg.select("#" + "yAxis").remove();
              svg.append("g")
                     .attr("id", "yAxis")
                     .style("font", "10px roboto")
                     .call(d3.axisLeft(y).ticks(6));


              var activeChannels = theData.channels
                     .filter(c => ! isEqCT( theData.lowerBounds[c],  theData.upperBounds[c] ))
                     .map(s => s.replace("EM_", ""));

              // Create the X axis for channels
              var xName = d3.scaleBand()
                     .domain(activeChannels)
                     .range([0, width]);
                     //.paddingInner(1)

              var channelWidth = Math.max(0, width / activeChannels.length); // width of each channel
              if (xAxes.length == 0 || xBoundsChanged) {
                     // X axis: minor axis for each channel
                     xAxes["major"] = d3.scaleBand()
                            .domain(activeChannels)
                            .range([0, width]);

                     svg.select("#" + "xAxis").remove();
                     svg.append("g")
                            .attr("transform", "translate(" + 0 + "," + height + ")")
                            .style("font", "10px roboto")
                            .attr("id", "xAxis")
                            .call(d3.axisBottom(xAxes["major"]));

                     activeChannels.forEach(c => {
                            //svg.select("#x" + c + "Axis").remove();
                            xAxes[c] = d3.scaleLinear()
                                   .domain([theData.lowerBounds[c], theData.upperBounds[c]])
                                   .range([0, channelWidth]);

                     });
              }

              activeChannels.forEach(c => {
                     svg.selectAll("#trace" + c).remove();
                     svg.append("path")
                            .datum(myData)
                            .attr("id", "trace" + c)
                            .attr("d", d3.line()
                              .x(function(d) {  var x = xAxes["major"](c) + xAxes[c](d["EM_" + c]); 
                                   return(x); })
                              .y(function(d) {  var yy = /*height -*/ y(d.time);  // fixme - is this right direction?
                                         return(yy); })
                            )
                            .style("stroke", "#69b3a2")
                            .style("fill", "none");
                     svg.selectAll("#xlow" + c).remove();
                     svg.append("text")
                            .attr("id", "xlow" + c)
                            .attr("x", xAxes["major"](c))
                            .attr("y", height - 13)
                            .attr("dx", 5)
                            .attr("dy", 10)
                            .attr("text-anchor", "start")
                            .text(theData.lowerBounds[c])
                            .style("font", "10px roboto");
                     svg.selectAll("#xhigh" + c).remove();
                     svg.append("text")
                            .attr("id", "xhigh" + c)
                            .attr("x", xAxes["major"](c) + channelWidth)
                            .attr("y", height - 13)
                            .attr("dx", -5)
                            .attr("dy", 10)
                            .attr("text-anchor", "end")
                            .text(theData.upperBounds[c])
                            .style("font", "10px roboto");
                     svg.append("line")
                            .attr("id", "xhigh" + c)
                            .attr("x1", xAxes["major"](c) + channelWidth)
                            .attr("x2", xAxes["major"](c) + channelWidth)
                            .attr("y1", y(tBegin))
                            .attr("y1", y(tEnd))
                            .style("stroke", "#aaaaaa")
                            .style("fill", "none");
              });
       }


       exports.version = version;
       exports.initData = initData;
       exports.addData = addData;

       Object.defineProperty(exports, '__esModule', { value: true });

})));

