# align observation points to plot numbers, throw away the rest.
##EM Buggy=group
##Clip to plot boundary=name
##data=vector
##boundary=vector
# width of buffer zone in m
##bufferWidth= number 0.2

##ClippedOutput=output vector

library(dplyr)
library(sf)
library(geosphere)



#dataPath <- "Dualem1HS_26062024_Wheat.All.shp"
#boundaryPath <- "~/work/Projects/GRDC Roots 2023/Trial Layout/New_Shapefile(4).shp"

#boundaryPath2 <- "/home/uqpdevo1/Downloads/Layout Wheat Trial 2024 Gatton.kmz"
#kmlFile <- file.path(dirname(boundaryPath2), "doc.kml")
#system2("unzip", args=c("-p", shQuote(boundaryPath2), "doc.kml"), stdout=kmlFile)
#bdy2 <- st_zm(st_read(kmlFile))

df <- data
bdy <- boundary %>% st_transform(crs="wgs84")

# Find the "long" side of each rectangle and squeeze from the ends.
# 1: top left
# 2: bottom left
# 3: bottom right
# 4: top right.
# 5: = 1
# fixme - see if this order is standard..
offsetCoords <- function(p) {
  stopifnot(nrow(p) == 5)
  res <- p[,1:2]
  d1 <- distGeo(res[1,], res[2,])
  d2 <- distGeo(res[2,], res[3,])
  if (d2 > d1) {
    #d2 is the longer side
    b <- bearingRhumb(res[2,], res[3,])
    res[1,] <- destPoint(res[1,], b, bufferWidth)
    res[2,] <- destPoint(res[2,], b, bufferWidth)
    res[3,] <- destPoint(res[3,], b-180, bufferWidth)
    res[4,] <- destPoint(res[4,], b-180, bufferWidth)
  } else {
    #d1 is the longer side
    b <- bearingRhumb(res[1,], res[2,])
    res[1,] <- destPoint(res[1,], b, bufferWidth)
    res[4,] <- destPoint(res[4,], b, bufferWidth)
    res[2,] <- destPoint(res[2,], b-180, bufferWidth)
    res[3,] <- destPoint(res[3,], b-180, bufferWidth)
  }
  res[5,] <- res[1,]
  res <- cbind(res, p[,3:ncol(p)])
  return(res)
}

# Make buffered polygons
buff <- bdy
for (i in 1:nrow(buff)) {
  buff$geometry[i] <- st_polygon(list( offsetCoords(st_coordinates(buff$geometry[i]))))
}

# clip
result <- st_filter(df, buff)

# add plot IDs
# fixme: some of the boundaries have no ID
if (all(buff$Id == 0)) {  buff <- buff %>% mutate(Id = row_number()) }
result$Id <- NA
IdLists <- st_intersects(buff, result)
for(i in 1:length(IdLists)) {
  for (j in IdLists[i]) {
    result$Id[ j  ] <- buff$Id[i]
  }
}

ClippedOutput <- result


