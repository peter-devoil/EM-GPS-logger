##EM Buggy=group
##Calc Boom Offset=name
##data=vector
# right distance of boom from GPS reciever
##boomRight=number 3.5
# trailing
##boomTrailing=number 1
# whether to remove duplicates or not
##removeDuplicates= number 1
# length within which to consider vehicle has stopped
##stoppingDistance= number 0.33
##Output=output vector

library("dplyr")
library("sf")
library("geosphere")

# Misc functions
# return a lat/long point offset from point
# bearing in degrees
# distance in meters
offset <- function(longitude, latitude, bearing, distance) {
  R=6378000         # This is in meters
  brng = bearing * pi / 180 # Bearing is converted to radians.
  lat1 = latitude * pi / 180 #Current lat point converted to radians
  lon1 = longitude * pi / 180 #Current long point converted to radians
  
  lat2 = asin( sin(lat1) * cos(distance/R) +
                 cos(lat1) * sin(distance/R) * cos(brng))
  
  lon2 = lon1 + atan2(sin(brng)*sin(distance/R)*cos(lat1),
                      cos(distance/R)-sin(lat1)*sin(lat2))
  
  lat2 = lat2 * 180 / pi
  lon2 = lon2 * 180 / pi
  return(data.frame(Longitude = lon2, Latitude=lat2))
}

# The (statistical) mode of a vector
Mode <- function(x) {
  ux <- unique(x)
  ux[which.max(tabulate(match(x,ux)))]
}


df <- data %>%
  rename_at(vars(starts_with('EM.')),  ~ sub("^EM\\.", "", .x)) %>%
  select(-starts_with("Operator")) %>%
  rename_at(vars(ends_with('.2')),  ~ sub("\\.2$", "", .x)) %>%
  select(-c(ends_with('.1'))) %>%
  mutate(Latitude = as.numeric(Latitude),
         Longitude = as.numeric(Longitude),
         Latitude = ifelse (Latitude < 0, Latitude, Latitude * -1)) %>%
  filter(Latitude != 0, Longitude != 0)

for (n in names(df)) {
   if (class(df[[n]]) == "character" &&
       !is.na(suppressWarnings(as.numeric(df[[n]][1])))) {
     df[[n]] = as.numeric( df[[n]] )
   }
}

#1. determine tracklines
if (all(df$Track == 0)) {
    # This GPS doesnt have track/bearing
    # calculate it over a running window of width 0.5m,
    # and remove points where the buggy has stopped
    df$Track2 <- NA
    for (i in 1:nrow(df)) {
      for (j1 in i:1) {
        d <- distGeo(c(df$Longitude[i], df$Latitude[i]), 
                     c(df$Longitude[j1], df$Latitude[j1]))
        if (d > 0.25) { # all obsns within 0.5m prior
          break
        }
      }
      for (j2 in i:nrow(df)) {
        d <- distGeo(c(df$Longitude[i], df$Latitude[i]), 
                     c(df$Longitude[j2], df$Latitude[j2]))
        if (d > 0.25) { # all obsns within 0.5m after
          break
        }
      }
      if (j2 > j1) {
        b <- bearingRhumb(c(df$Longitude[j1], df$Latitude[j1]), 
                          c(df$Longitude[j2], df$Latitude[j2]))
        df$Track2[i] <- b
      }
    }
    df <- df %>% 
      rename(Track = "Track2")
}

if (removeDuplicates != 0) {
  # same again, but calculate the number nearby
  for (i in 1:nrow(df)) {
    for (j1 in i:1) {
      d <- distGeo(c(df$Longitude[i], df$Latitude[i]), 
                   c(df$Longitude[j1], df$Latitude[j1]))
      if (d > stoppingDistance / 2) { # all obsns within X m prior
        break
      }
    }
    for (j2 in i:nrow(df)) {
      d <- distGeo(c(df$Longitude[i], df$Latitude[i]), 
                   c(df$Longitude[j2], df$Latitude[j2]))
      if (d > stoppingDistance / 2) { # all obsns within X m after
        break
      }
    }
    if (j2 > j1) {
      df$nNear[i] <- j2 - j1
    }
  }
  
  # remove points where stationary, leave one in the middle
  df$stationary <- 0    # 0 if moving, group number (1..n) otherwise
  inStop <- df$nNear[1] > 10
  stopNum <- 1
  for (i in 1:nrow(df)) {
     if (inStop && df$nNear[i] > 10) {
        df$stationary[i] <- stopNum
     } else if (!inStop && df$nNear[i] > 10) {
        df$stationary[i] <- stopNum
        inStop <- T
     } else if (inStop && df$nNear[i] <= 10) {
        df$stationary[i] <- 0
        inStop <- F
        stopNum <- stopNum + 1
     } else {
        df$stationary[i] <- 0
        inStop <- F
     }
  }
    
  # remove stationary points, leave one in the middle
  df <- df %>% 
    group_by(stationary) %>%
    mutate(mid = row_number() == ceiling(n()/2)) %>%
    filter(stationary == 0 | mid) %>%
    ungroup() %>%
    select(-c(mid, stationary)) 
  cat ("Removed ",  stopNum, " stopped groups") 
}

# Find the predominate track lines: the top two bins
b1 <- sort(table(cut(df$Track,20)), decreasing = T)  # bins
b2 <- names(head(b1,2)) # top two most common as simple numeric numbers
splitPoint <- mean(as.numeric(unlist(lapply(strsplit(gsub("\\(|]$", "", b2), ","),first)))) # The midpoint between the humps
df$roughTrack <- 5 * round(df$Track / 5, 0)  # bin to 5 degrees
B1 <- Mode(df$roughTrack[df$Track < splitPoint]) # most common
B2 <- Mode(df$roughTrack[df$Track >= splitPoint])
df$roughBearing <- ifelse(df$Track < splitPoint, B1, B2)
  
# 2. calculate boom offset from centerlines
t1 <- offset(df$Longitude, df$Latitude, df$roughBearing, - boomTrailing)  
t2 <- offset(t1$Longitude, t1$Latitude, df$roughBearing + 90, boomRight)  

# update to offset positions
df$Longitude <- t2$Longitude
df$Latitude <- t2$Latitude

# calculate time since start
df <- df %>%
  mutate(DateTime = as.POSIXct(paste(YYYY.MM.DD, HH.MM.SS.F),  
                               format="%Y-%m-%d %H:%M:%S"),
         TimeSinceStart = as.numeric(DateTime - min(DateTime))) 


Output <- st_as_sf(df, coords = c("Longitude", "Latitude"), crs = "WGS84")
