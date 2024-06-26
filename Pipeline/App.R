library(shiny)
library(dplyr)
library(leaflet)
library(mapedit)
library(ggplot2)
library(shinybusy)
library(sf)

ui <- fluidPage(
  #add_busy_spinner(spin = "fading-circle", position="full-page"),
  tabsetPanel(
    tabPanel("Data", 
             fluidRow(
               column(6, 
                      fileInput("upload", "Data", buttonLabel = "Open"),
                      wellPanel(style = "overflow-x: scroll;height:80vh;overflow-y: scroll;",
                                tableOutput("preview"))
                      # fixme - table needs to editable to remove rows
               ),
               column(6, 
                      downloadButton("downloadData", "Download"),
                      br(),
                      radioButtons("downloadType", "Aggregation", 
                                   c("None", "Plot Average", "Centroid"))
               )
             )
    ),
    tabPanel("Geo Screen",
             fluidRow(
               column(width=6, 
                  fluidRow(
                      column(width=3, 
                             fileInput("uploadPlotBoundaries", "Plot boundaries", buttonLabel = "Open"),
                             numericInput("borderWidth", "Plot Border Width (m)", value = 0.2)),
                      column(width=3, offset = 3, 
                             numericInput("boomRight", "Boom right offset (m)", value = 2.8),
                             numericInput("boomTrailing", "Boom trailing offset (m)", value = 1.0))),
                  wellPanel(style = "height: 60vh;",
                            leafletOutput("geomap", height="100%"))
               ),
               column(width=6, 
                      wellPanel(style = "overflow-x: scroll;height:80vh;overflow-y: scroll;",
                                tableOutput("geogrid")))
             )
    ),
    tabPanel("Em Screen",
             fluidRow(
               column(6, 
                      wellPanel(style = "height: 60vh;",
                                leafletOutput("emmap"))
               ),
               column(6, 
                      selectInput("emWhat", label = "Channel", 
                                  choices = c("PRP1","PRP2","PRPH","HCP1","HCP2","HCPH","PRPI1","PRPI2","PRPIH"),
                                  selected="PRP1"),
                      br(),
                      plotOutput("emHist", height = "30vh", width = 500),
                      br(),
                      plotOutput("emBox", height = "30vh", width = 300)
               )
             )
           )
    )
)

# Read a .csv file recorded from the buggy
readRawData <- function(datapath) {
  read.csv(datapath, sep = ",", header=T) %>%
    mutate(DateTime = as.POSIXct(paste(YYYY.MM.DD, HH.MM.SS.F),  
                                 format="%Y-%m-%d %H:%M:%S")) %>%  # Ignores fractional seconds
    rename_at(vars(starts_with('EM.')),  ~ sub("^EM\\.", "", .x)) %>%
    select(-c(`YYYY.MM.DD`, `HH.MM.SS.F`), -starts_with("Operator")) %>%
    relocate(DateTime) %>%
    rename_at(vars(ends_with('.2')),  ~ sub("\\.2$", "", .x)) %>%
    select(-c(ends_with('.1'))) %>%
    mutate(Latitude = ifelse (Latitude < 0, Latitude, Latitude * -1)) %>%
    filter(Latitude != 0, Longitude != 0)
}

# Statistical mode of a vector
Mode <- function(x) {
  ux <- unique(x)
  ux[which.max(tabulate(match(x, ux)))]
}

# return a lat/long point offset from point
# bearing in degrees
# distance in meters
offset <- function(longitude, latitude, bearing, distance) {
  R=6378000         # This is in meters
  
  #longitude <- st_coordinates(coord)[1]
  #latitude <-  st_coordinates(coord)[2]
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


doOffsetting <- function(p, boomRight, boomTrailing) {
  #1. determine tracklines
  b1 <- sort(table(cut(p$Track,20)), decreasing = T)  # bins
  b2 <- names(head(b1,2)) # top two most common as simple numeric numbers
  splitPoint <- mean(as.numeric(unlist(lapply(strsplit(gsub("\\(|]$", "", b2), ","),first)))) # The midpoint between the humps
  p$roughTrack <- 5 * round(p$Track / 5, 0)  # bin to 5 degrees
  B1 <- Mode(p$roughTrack[p$Track < splitPoint]) # most common
  B2 <- Mode(p$roughTrack[p$Track >= splitPoint])
  p$roughBearing <- ifelse(p$Track < splitPoint, B1, B2)

  # 2.   
  t1 <- offset(p$Longitude, p$Latitude, p$roughBearing, - boomTrailing)  
  t2 <- offset(t1$Longitude, t1$Latitude, p$roughBearing + 90, boomRight)  
  p$Longitude <- t2$Longitude
  p$Latitude <- t2$Latitude
  return(p)
}


server <- function(input, output, session) {
  data <- reactive({
    req(input$upload)
    ext <- tools::file_ext(input$upload$name)
    if (ext != "csv") { validate("Invalid file; Please upload a .csv file") }
    readRawData(input$upload$datapath)
  })
  
  getPlotBoundaries <- reactive({
    req(input$uploadPlotBoundaries)
    ext <- tools::file_ext(input$uploadPlotBoundaries$name)
    result <- NULL
    
    if (tolower(ext) == "kml") {result <- st_zm(st_read(input$uploadPlotBoundaries$datapath)) } 
    if (tolower(ext) == "kmz") {
      kmlFile <- file.path(dirname(input$uploadPlotBoundaries$datapath), "doc.kml")
      system2("unzip", args=c("-p", shQuote(input$uploadPlotBoundaries$datapath), "doc.kml"), stdout=kmlFile)
      result <- st_zm(st_read(kmlFile))
    }
    if (is.null(result)) { validate("Invalid file; Please upload a .kml|z file")}
    result
  })
  
  geoScreenedData<- reactive({
    data()
  })
  
  emScreenedData<- reactive({
    geoScreenedData()
  })
  
  downloadData<- reactive({
    emScreenedData()
  })

  geoBoundaries<- reactive( {
    getPlotBoundaries()
  })
  
  geoPoints<- reactive( {
    req(input$borderWidth)
    b <- getPlotBoundaries()
    p <- data()

    if (TRUE) { # (input$doBoomOffset) 
      p <- doOffsetting(p, input$boomRight, input$boomTrailing)
    }
    return(p)
    #getActive(, input$borderWidth) 
  })
  
  # show preview of raw data
  output$preview <- renderTable({
    data() %>% mutate(DateTime = format.POSIXct(DateTime, format="%d/%m/%Y %H:%M.%S"))
  })
   
   # Downloadable csv of selected dataset ----
   output$downloadData <- downloadHandler(
     filename = function() {
       paste(input$upload$name, ".Screened.csv", sep = "")
     },
     content = function(file) {
       write.csv(downloadData(), file, row.names = FALSE)
     }
   )
  
  output$geogrid <- renderTable({
    geoScreenedData() %>% mutate(DateTime = format.POSIXct(DateTime, format="%d/%m/%Y %H:%M:%S"))
  })
  
  output$geomap <- renderLeaflet({
    leaflet(options = leafletOptions(preferCanvas = TRUE)) %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)",
               options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) #%>%
      #addPmToolbar(targetGroup = "points", drawOptions =  pmDrawOptions())
  })
  
  observe({
    plotBoundaries <<- geoBoundaries()
    bbox <- as.numeric(st_bbox(plotBoundaries))
    leafletProxy("geomap") %>%
      clearGroup("boundaries") %>%
      setView(lat = (bbox[2] + bbox[4]) /2, lng = (bbox[1] + bbox[3]) /2, zoom = 16)  %>%
      addPolygons(data = plotBoundaries, group = "boundaries", fill = NA, weight = 1, color = "red") 
  })  
  
  observe({
    p <- geoPoints()
    if (all(!is.na(p$Longitude) & !is.na(p$Latitude))) {
      plotPoints <<- st_as_sf(p, coords = c("Longitude", "Latitude"), 
                            crs = "WGS84") #st_crs(boundaries))
      leafletProxy("geomap") %>%
        clearGroup("points") %>%
        addCircleMarkers(data = plotPoints, group = "points", 
                         layerId =  paste0("point", 1:nrow(plotPoints)),
                         radius=4, stroke=FALSE, fillOpacity=1.0, fillColor = "green") 
      # fixme add selected / not selected colours
    }
  })
  
  output$emmap <- renderLeaflet({
    leaflet(options = leafletOptions(preferCanvas = TRUE)) %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)",
               options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) #%>%
    #addPmToolbar(targetGroup = "points", drawOptions =  pmDrawOptions())
  })
  
  observe({
    plotBoundaries <<- geoBoundaries()
    bbox <- as.numeric(st_bbox(plotBoundaries))
    leafletProxy("emmap") %>%
      clearGroup("boundaries") %>%
      setView(lat = (bbox[2] + bbox[4]) /2, lng = (bbox[1] + bbox[3]) /2, zoom = 16)  %>%
      addPolygons(data = plotBoundaries, group = "boundaries", fill = NA, weight = 1, color = "red") 
  })  
  
  observe({
    p <- geoPoints()
    if (all(!is.na(p$Longitude) & !is.na(p$Latitude))) {
      plotPoints <<- st_as_sf(p, coords = c("Longitude", "Latitude"), 
                              crs = "WGS84") #st_crs(boundaries))
      leafletProxy("emmap") %>%
        clearGroup("points") %>%
        addCircleMarkers(data = plotPoints, group = "points", 
                         layerId =  paste0("point", 1:nrow(plotPoints)),
                         radius=4, stroke=FALSE, fillOpacity=1.0, fillColor = "green") 
      # fixme add selected / not selected colours
    }
  })
  
  output$emHist <- renderPlot({
    data <- emScreenedData()
    if (!is.null(data)) {
      return(
        ggplot( data ) + 
          geom_histogram(aes(x = .data[[input$emWhat]] ))
      )
    }
  })

  output$emBox <- renderPlot({
    data <- emScreenedData()
    if (!is.null(data)) {
      return(
        ggplot(data) + 
          geom_boxplot(aes(y = .data[[input$emWhat]] ))
      )
    }
  })
  
  #observe({
  #  input$reset_button
  #  leafletProxy("geomap") %>% setView(lat = initial_lat, lng = initial_lng, zoom = initial_zoom)
  #})
}

shinyApp(ui, server)
