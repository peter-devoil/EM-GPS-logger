(function (global, factory) {
       typeof exports === 'object' && typeof module !== 'undefined' ? factory(exports) :
              typeof define === 'function' && define.amd ? define(['exports'], factory) :
                     (factory((global.myHist = global.myHist || {})));
}(this, (function (exports) {
       'use strict';

       var version = "0.0.1";

       // set the dimensions and margins of the graph
       var width = -1;
       var height = -1;
       //var emData = null;
       
       var reColourFunction = null;

       function setRecolour (f) { reColourFunction = f; }

       // get the data
       function loadEMData( emData ) {
           //emData = _emData;
           var channels = Object.getOwnPropertyNames(emData.features[0].properties)
              .filter(c => c.indexOf("PRP") >=0 || c.indexOf("HCP") >=0);

           emData.lowerBounds = [];
           emData.upperBounds = [];
           channels.forEach(c => {
              var thisChan = [];
              emData.features.forEach((feature) => {
                     var x = feature.properties[c];
                     var value;
                     if (typeof x === 'string' || x instanceof String) 
                         value = parseFloat(x);
                     else
                         value = x;
                     if (isFinite(value)) {
                            thisChan.push(value);
                     }
              });

              const sum = arr => arr.reduce((partialSum, a) => partialSum + a, 0);
              const mean = arr => sum(arr) / arr.length;
              const variance = arr => {
                     const m = mean(arr);
                     return (sum(arr.map(v => (v - m) ** 2)) / arr.length);
                 };
              const sd = arr => Math.sqrt(variance(arr));
              
              var m = mean(thisChan);
              var stdd = sd(thisChan);

              emData.lowerBounds[c] = m - 2 * stdd;
              emData.upperBounds[c] = m + 2 * stdd;
           });
       }

       // keep these around for later..
       var x = null;
       var y = null;
       function drawData(element, msgElement, emData) {
              element.replaceChildren();

              var margin = { top: 10, right: 30, bottom: 30, left: 40 };

              width = /*element.clientWidth*/ 400 - margin.left - margin.right;
              height = /*element.clientHeight*/ 300 - margin.top - margin.bottom;

              if (width <= 0 || height <= 0) { console.log("zero WH"); return; }

              var svg = d3.select(element)
                     .append('svg')
                     .classed("svg-content-responsive", true)
                     .attr("preserveAspectRatio", "xMidYMid meet")
                     .attr("viewBox", "0 0 400 400")
                     //.attr("width", width + margin.left + margin.right)
                     .append("g")
                     .attr("viewBox", margin.top + " " + margin.left + " " + width + " " + height)
                     .attr("transform",
                            "translate(" + margin.left + "," + margin.top + ")");

              var thisData = [];
              emData.features.forEach((feature) => {
                     var x = feature.properties[emData.selectedChannel];
                     var value;
                     if (typeof x === 'string' || x instanceof String) 
                         value = parseFloat(x);
                     else
                         value = x;
                     if (isFinite(x)) {
                            thisData.push(x);
                     }
              });

              if (thisData.length == 0 ||
                  thisData.some((x) => { !isFinite(x) })) {
                     msgElement.innerHTML = "&nbsp;NaN in, or no data"; return;
              }

              var min = Math.min(emData.lowerBounds[emData.selectedChannel], d3.min(thisData));
              var max = Math.max(emData.upperBounds[emData.selectedChannel], d3.max(thisData));

              // X axis: scale and draw:
              x = d3.scaleLinear()
                     .domain([min, max])
                     .range([0, width]);

              svg.append("g")
                     .attr("transform", "translate(0," + height + ")")
                     .style("font", "14px roboto")
                     .call(d3.axisBottom(x));

              // set the parameters for the histogram
              var histogram = d3.histogram()
                     .value(function(d) { return(d);})
                     .domain(x.domain())
                     .thresholds(x.ticks(50)); // bins

              // And apply this function to data to get the bins
              var bins = histogram(thisData);

              // Y axis: scale and draw:
              y = d3.scaleLinear()
                     .range([height, 0])
                     .domain([0,
                              d3.max(bins, function (d) { return d.length; })]);

              svg.append("g")
                     .call(d3.axisLeft(y));

              // append the bar rectangles to the svg element
              svg.selectAll("rect")
                     .data(bins)
                     .enter()
                     .append("rect")
                     .attr("x", function(d) { return x(d.x0); })
                     .attr("y", function(d) { return y(d.length); })
                     .attr("height", function(d) { return y(0) - y(d.length); })
                     .attr("width", function (d) { return x(d.x1) - x(d.x0) - 1; })
                     .style("fill", "#69b3a2")

              // draggable bounds
              const lowerBound = svg.append("g")
                     .append("rect")
                     .attr("x", x(emData.lowerBounds[emData.selectedChannel]))
                     .attr("y", 0)
                     .attr("width", 2)
                     .attr("height", height)
                     .attr("id", "lower")
                     .style("fill", "blue")
                     .style("stroke", "blue")
                     .style("cursor", "ew-resize")
                     .call(d3.drag()
                            .on("drag", (e,d) => dragging("lower", e, d))
                            .on("end", (e,d) => dragging("lower", e, d)));

              const upperBound = svg.append("g")
                     .append("rect")
                     .attr("x", x(emData.upperBounds[emData.selectedChannel]))
                     .attr("y", 0)
                     .attr("width", 2)
                     .attr("height", height)
                     .attr("id", "upper")
                     .style("fill", "red")
                     .style("stroke", "red")
                     .style("cursor", "ew-resize")
                     .call(d3.drag()
                            .on("drag", (e,d) => dragging("upper", e, d))
                            .on("end", (e,d) => dragging("upper", e, d)));
              function dragging(what, event, d) {
                     var newX = x.invert(Math.max(0, Math.min(width, event.x)));
                     if (what == "upper") {
                            emData.upperBounds[emData.selectedChannel] = newX;
                            svg
                                   .select("#" + what)
                                   .attr("x", x(newX))
                     } else if (what == "lower") {
                            emData.lowerBounds[emData.selectedChannel] = newX;
                            svg
                                   .select("#" + what)
                                   .attr("x", x(newX))
                     }
                     showTextSummary(msgElement, thisData, emData);
              }
              showTextSummary(msgElement, thisData, emData);
       }

       // called when entry x.yyy is changed
       function updateBounds(histElement, msgElement, emData) {
              var svg = d3.select(histElement)
                     .selectChild('svg');
              svg
                     .select("#" + "lower")
                     .attr("x", x(emData.lowerBounds[emData.selectedChannel]));
              svg
                     .select("#" + "upper")
                     .attr("x", x(emData.upperBounds[emData.selectedChannel]));

       }

       function showTextSummary(element, data, emData) {
              const sum = arr => arr.reduce((partialSum, a) => partialSum + a, 0);
              var numLow = sum(data.map(d => d < emData.lowerBounds[emData.selectedChannel]));
              var pcntLow = Math.round(100 * numLow / data.length);
              var numHigh = sum(data.map(d => d > emData.upperBounds[emData.selectedChannel]));
              var pcntHigh = Math.round(100 * numHigh / data.length);

              document.querySelector('#lowBoundInput')
                     .value = Math.round(emData.lowerBounds[emData.selectedChannel] * 100) / 100;  //??
              document.querySelector('#lowBoundMsg')
                     .innerHTML = "n screened = " + numLow + " (" + pcntLow + "%)";

              document.querySelector('#highBoundInput')
                     .value = Math.round(emData.upperBounds[emData.selectedChannel] * 100) / 100;
              document.querySelector('#highBoundMsg')
                     .innerHTML = "n screened = " + numHigh + " (" + pcntHigh + "%)";

              if (reColourFunction != null) {
                     reColourFunction();
              }
       }


       exports.version = version;
       exports.loadEMData = loadEMData;
       exports.drawData = drawData;
       exports.setRecolour = setRecolour;
       exports.updateBounds= updateBounds;
       
       Object.defineProperty(exports, '__esModule', { value: true });

})));

