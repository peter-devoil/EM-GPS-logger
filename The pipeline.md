The [data collection app](./Dualem_and_GPS_datalogger.py) leaves two csv files: one of point data (where the user has pressed a button over sample points), and a continuous recording of the sensor while driving over the experiment.

The former can be analysed directly, the latter requires geolocation and aggregation to plot level before further use. This occurs in QGIS, with the help of a few R scripts.

### The pipeline (QGis)
QGIS has an R plugin called the "R processing engine". If you cannot see R in the Processing Toolbox, you have to activate it in Processing ► Options ► Providers

## Install the R scripts
Copy the rsx files to the QGIS R processing plugin directory (set via Settings/Options - see qgis-setup-1.png).

## Run the Offset Boom 
The script is in the R Processing toolbox/

Set your input csv data by choosing the "Select Input" icon with 3 dots on the right and finding the csv file. The spanner icon gives you an option turn off invalid feature filtering (which will be needed with early files). Check the boom position (right distance & trailing) matches yours.

Your output data should appear as a set of points where the buggy was driven. 

There is an option to remove repeat observations where the buggy stopped (>5s of no movement).

Associated is the distance to consider "stopped" - points within this distance are grouped together and all bar the central (in time) observation are removed.

At this point, it is worth examining the points created to be sure that we're ready to progress. Using a colour gradient to identify time since the start of the run (TimeSinceStart) can highlight where the GPS tracking signal is reversing direction.

## Clip to boundaries
Another script ("Clipping ... ") will clip the observations to the inside of the plot boundaries. This time, select data as the layer you have just created, and also specify the shapefile or layer of plot boundaries. The "buffer width" parameter removes observations from both ends of each plot.

## Chart
TBD

### The pipeline (R)
Two scripts equivalent to the above are written. Parameters are at the top of the file. The first script (Offset) creates a shapefile (.shp). The second a (Clipped.shp) file.
