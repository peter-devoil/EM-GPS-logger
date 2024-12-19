library("dplyr")
library("sf")
library("geosphere")

# Generate plot boundaries. Laneways & buffers are unassigned

# The top and bottom - left edge. 

p1 <- c(152.33121288,-27.54503772)
p2 <- c(152.331773296,-27.546300752) 

# Plot width & length (m)
pWidth<- 2
pLength <- 6

# The column widths of both plots and laneways (space between plots)
colWidths <- rep( c(pWidth, pWidth, pWidth), 12)
# True if the column is a laneway
laneColumns <- rep( c(F,F,T), 12)

# The length of each plot
rowLengths <- rep(c(rep(pLength, 6), 2), 4)
# Whether the row is a laneway
laneRows <- rep(c(rep(F, 6), T), 4)

# Check
stopifnot(length(colWidths) == length(colWidths))

# Bearing in degrees north
b <- bearing(p1, p2)  

# Make a list of plots. 'id' is the NW:SE sequence number
plots<- list()
iRow <- 1;
iCol <- 1;
id <- 1

while(T) {
   # Generate a polygon of the plot boundaries
   if (!laneColumns[iCol] && !laneRows[iRow]) {
      xoff <- ifelse(iRow == 1, 0, sum(rowLengths[1:(iRow-1)]))
      yoff <- ifelse(iCol == 1, 0, sum(colWidths[1:(iCol-1)]))
      p <- destPoint(destPoint(p1, b, xoff), b - 90, yoff)
      
      plt1<- matrix(p, nrow=1)
      plt2<- destPoint(plt1, b, rowLengths[iRow])
      plt3<- destPoint(plt2, b - 90, colWidths[iCol])
      plt4<- destPoint(plt1, b - 90, colWidths[iCol])

      poly <- do.call(rbind, list(plt1,plt2,plt3,plt4))
      plots[[id]] <- cbind(poly, seq=1:4, id=id)
      id <- id + 1
   }
  
   # Work out if we've reached the end of a row/column
   iRow <- iRow + 1
   if (iRow > length(rowLengths)) {
     iRow <- 1
     iCol <- iCol + 1
     if (iCol > length(colWidths)) {
        break
     }
   }
}

# Convert to spatial object
result <- data.frame(do.call(rbind, plots)) %>%
  sf::st_as_sf(coords = c("lon", "lat"), crs = "wgs84") %>%
  group_by(id) %>%
  arrange(seq) %>%
  summarize(do_union = FALSE) %>%
  st_cast("POLYGON")

# Write
write_sf(result, "makePlotBoundaries.shp")

library(ggplot2)
ggplot(result) + geom_sf()
