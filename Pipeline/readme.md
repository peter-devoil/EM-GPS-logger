1. Clean up raw data from EM app
- app: change to oNorth, use hemisphere from nmea string
- outliers: lat/long 0 or outside study zone
- remove outside [plot + boom], ie turning bays
- correct for boom offset (1m S + 2.5m W). Use heading/track?

- preview (via map) & save

2. identify & remove prp1,2, hcp1,2 outliers:
- outliers as histograms & boxplots
- identify outliers on a map

3. extraction - from raw observations to inversion
- all individual points after cleaning
- plot averages (after inner boundary removal eg 20cm 
  from edges) and centroid value.
 