library(shiny)
library(bslib)
#library(DT)
library(rhandsontable)
library(dplyr)
library(leaflet)
library(leaflet.extras)
library(mapedit)
library(ggplot2)
library(shinybusy)
library(sf)

ui <- page_sidebar(
  title ="EM Screening",
  #add_busy_spinner(spin = "fading-circle", position="full-page"),
  sidebar = sidebar(
    fileInput("upload", "EM Data", buttonLabel = "Open"),
    fileInput("uploadPlotBoundaries", "Plot boundaries", buttonLabel = "Open"),
    numericInput("borderWidth", "Plot Border Width (m)", value = 0.2),
    numericInput("boomRight", "Boom right offset (m)", value = 2.8),
    numericInput("boomTrailing", "Boom trailing offset (m)", value = 1.0),
    br(),
    downloadButton("downloadData", "Download"),
    radioButtons("downloadType", "Aggregation", 
                 c("None", "Plot Average", "Centroid"))
  ),
  fluidRow(
    column(width=6, 
           wellPanel(style = "height: 60vh;",
                     leafletOutput("geomap", height="100%")),
           br(),
           fluidRow(column(6, align = "center", offset=3,
           actionButton("move", label = tags$span(
             "", tags$i(
               class = "fa fa-right-left",
               title = "Move selected"
             ))),
           actionButton("accept", label = tags$span(
             "", tags$i(
               class = "fa fa-check",
               title = "Use selected"
             ))),
           actionButton("reject", label = tags$span(
             "", tags$i(
               class = "fa fa-xmark",
               title = "Discard selected"
             )))
           ))
    ),
    column(width=6, 
           navset_pill(
             nav_panel(title="Geo Screen",
                       wellPanel(style = "overflow-x: scroll;height:80vh;overflow-y: scroll;",
                                 #DT::dataTableOutput("geogrid"))
                                 rHandsontableOutput("geogrid"))
             ),
             nav_panel(title="EM Screen",
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
  markedIDs <- reactiveValues(screenedIDs = {}, selectedIDs = {})

  data <- reactive({
    req(input$upload)
    ext <- tools::file_ext(input$upload$name)
    if (ext != "csv") { validate("Invalid file; Please upload a .csv file") }
    cat("data() called\n")
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
  
  geoPoints<- reactive( {
    #req(markedIDs$selected, markedIDs$screened, input$boomRight, input$boomTrailing)
    #b <- getPlotBoundaries()
    p <- data()
    # fixme - what to do with input$borderWidth?
    if (TRUE) {
       p <- doOffsetting(p, input$boomRight, input$boomTrailing)
    }
    
    return(st_as_sf(p, coords = c("Longitude", "Latitude"), crs = "WGS84") %>%
           mutate(id = paste0("point", row_number()))
    )
  })
  
   # Downloadable csv of selected dataset ----
   output$downloadData <- downloadHandler(
     filename = function() {
       paste(input$upload$name, ".Screened.csv", sep = "")
     },
     content = function(file) {
       screenedData <- data() %>% filter(!row_number() %in% markedIDs$screened)
       write.csv(screenedData, file, row.names = FALSE)
     }
   )
  output$geogrid <- renderRHandsontable({ 
    df <- data() %>%
      mutate(DateTime = format.POSIXct(DateTime, format="%d/%m/%Y %H:%M:%S"),
             screened = row_number() %in% markedIDs$screened)
    rhandsontable(df, useTypes = T) 
  })
  
  output$geogridOLD <- renderDataTable({
    data() %>%
      mutate(DateTime = format.POSIXct(DateTime, format="%d/%m/%Y %H:%M:%S"),
             screened = row_number() %in% markedIDs$screened)
  })
  
  output$geomap <- renderLeaflet({
    leaflet(options = leafletOptions(preferCanvas = TRUE)) %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)",
               options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE, minzoom=4, maxZoom=24, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addDrawToolbar(polylineOptions = F, circleOptions = F, markerOptions = F,
                     circleMarkerOptions = F, polygonOptions = F, 
                     rectangleOptions = drawRectangleOptions(), targetGroup='selection-marker')
  })
  
  observe({
    plotBoundaries <- getPlotBoundaries()
    bbox <- as.numeric(st_bbox(plotBoundaries))
    leafletProxy("geomap") %>%
      clearGroup("boundaries") %>%
      setView(lat = (bbox[2] + bbox[4]) /2, lng = (bbox[1] + bbox[3]) /2, zoom = 16)  %>%
      addPolygons(data = plotBoundaries, group = "boundaries", fill = NA, weight = 1, color = "red") 
  })  
  
  observe({
    plotPoints <- geoPoints() 
    bbox <- as.numeric(st_bbox(plotPoints))
    # fixme test if new data was loaded, if so then reset view    
    activePoints <- plotPoints %>% filter(!row_number() %in% markedIDs$screened)
    deletedPoints <- plotPoints %>% filter(row_number() %in% markedIDs$screened)
    selectedPoints <- plotPoints %>% filter(row_number() %in% markedIDs$selected)
    leafletProxy("geomap") %>%
        clearGroup("points") %>%
        addCircleMarkers(data = deletedPoints, group = "points", 
                         layerId =  deletedPoints$id,
                         radius=4, stroke=FALSE, fillOpacity=1.0, fillColor = "grey") %>%
        addCircleMarkers(data = activePoints, group = "points", 
                         layerId =  activePoints$id,
                         radius=4, stroke=FALSE, fillOpacity=1.0, fillColor = "green") %>%
        addCircleMarkers(data = selectedPoints, group = "points", 
                         layerId =  selectedPoints$id,
                         radius=4, stroke=FALSE, fillOpacity=1.0, fillColor = "red")
  })
  
  observeEvent(input$geomap_draw_new_feature, {
    feat <- input$geomap_draw_new_feature
    coords <- matrix(unlist(feat$geometry$coordinates), ncol = 2, byrow = T)
    selBox <- st_sf(st_sfc(st_polygon(list(coords))), crs = "WGS84")

    selPoints <-  st_filter(plotPoints %>% mutate(selected = row_number()),
                            selBox)
    
    markedIDs$selected <- selPoints$selected
    
    leafletProxy("geomap") %>% clearGroup("selection-marker")  # fixme this isnt working
    
  })

  findIdNear <- function (point, distance) {
    return(which(as.vector(st_distance(plotPoints, point)) < distance))
  }
  
  observeEvent(input$geomap_click, {
    p <- st_as_sf(data.frame(lng = input$geomap_click$lng, lat = input$geomap_click$lat), 
                  coords=c("lng", "lat"), crs = "WGS84")
    ids <- findIdNear(p, 2) # fixme - should be pixel based wand here, not m
    markedIDs$selected <- unique(c(markedIDs$selected, ids))
    first(markedIDs$selected)
  })
  
  observeEvent(input$geomap_shape_click, { 
    p <- input$geomap_shape_click
    #cat("SHAPE\n"); print(p)
  })
  observeEvent(input$move, {})
  observeEvent(input$accept, {
    if (length(markedIDs$selected) > 0) {
      markedIDs$screened <- markedIDs$screened[! markedIDs$screened %in% markedIDs$selected]
    }
    markedIDs$selected <- {}
  })
  observeEvent(input$reject, {
    if (length(markedIDs$selected) > 0) {
      markedIDs$screened <- unique(c(markedIDs$screened, markedIDs$selected))
    }
    markedIDs$selected <- {}
  })
  
    
  output$emHist <- renderPlot({
    myData <- data() %>% filter(!row_number() %in% markedIDs$screened)
    screenedData <- data() %>% filter(row_number() %in% markedIDs$screened)
    if (!is.null(myData)) {
      return(
        ggplot( myData ) + 
          geom_histogram(aes(x = .data[[input$emWhat]] ), bins=50)+ 
          geom_point(data=screenedData, aes(x = .data[[input$emWhat]]), y = 0,colour="brown")
        # fixme - should display selected as red, screened out as grey,
        #         calcultations should be on non-screeened data
      )
    }
  })

  output$emBox <- renderPlot({
    myData <- data() %>% filter(!row_number() %in% markedIDs$screened)
    screenedData <- data() %>% filter(row_number() %in% markedIDs$screened)
    if (!is.null(myData)) {
      return(
        ggplot(myData) + 
          geom_boxplot(aes(y = .data[[input$emWhat]] )) + 
          geom_point(data=screenedData, aes(y = .data[[input$emWhat]], x=0), colour="brown")
      )
    }
  })
}

shinyApp(ui, server)
