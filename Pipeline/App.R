library(shiny)
library(dplyr)
library(leaflet)
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
               column(6, 
                      fileInput("uploadPlotBoundaries", "Plot boundaries", buttonLabel = "Open"),
                      numericInput("borderWidth", "Plot Border Width (cm)", value = 20),
                      wellPanel(style = "height: 70vh;",
                                leafletOutput("geomap"))
               ),
               column(6, 
                      wellPanel(style = "overflow-x: scroll;height:80vh;overflow-y: scroll;",
                                tableOutput("geogrid"))
               )
             )
    ),
    tabPanel("Em Screen",
             fluidRow(
               column(6, 
                      wellPanel(style = "height: 70vh;",
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

# Read a .csv file
readRawData <- function(datapath) {
  read.csv(datapath, sep = ",", header=T) %>%
    mutate(DateTime = as.POSIXct(paste(YYYY.MM.DD, HH.MM.SS.F),  
                                 format="%Y-%m-%d %H:%M:%S")) %>%  # Ignores fractional seconds
    rename_at(vars(starts_with('EM.')),  ~ sub("^EM\\.", "", .x)) %>%
    select(-c(`YYYY.MM.DD`, `HH.MM.SS.F`), -starts_with("Operator")) %>%
    relocate(DateTime) %>%
    rename_at(vars(ends_with('.2')),  ~ sub("\\.2$", "", .x)) %>%
    select(-c(ends_with('.1'))) %>%
    mutate(Latitude = ifelse (Latitude < 0, Latitude, Latitude * -1))
}

server <- function(input, output, session) {
  data <- reactive({
    req(input$upload)
    ext <- tools::file_ext(input$upload$name)
    if (ext != "csv") { validate("Invalid file; Please upload a .csv file") }
    readRawData(input$upload$datapath)
  })
  
  plotBoundaries <- reactive({
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
  
  # path<-"/home/uqpdevo1/Downloads/Layout Wheat Trial 2024 Gatton.kmz"
  # path<-"/home/uqpdevo1/New_Shapefile(4).shp"
  # ext <- tools::file_ext(path)
  # result<- NULL
  # if (tolower(ext) == "shp") {result <- st_read(path ) } 
  # 
  # if (tolower(ext) == "kml") {result <- st_read(path) } 
  # if (tolower(ext) == "kmz") {
  #   kmlFile <- file.path(dirname(path), "doc.kml")
  #   system2("unzip", args=c("-p", shQuote(path), "doc.kml"), stdout=kmlFile)
  ##   result <- st_zm(st_read(kmlFile))
  # }
  # boundaries <- result
  # bbox <- as.numeric(st_bbox(boundaries))

  # data <- readRawData("/home/uqpdevo1/Downloads/WheatGatton2024.D1.10062024.csv")   
  # points <-  st_as_sf(data, coords = c("Longitude", "Latitude"), 
#                               crs = st_crs(boundaries), agr="constant")
   
  # leaflet(options = leafletOptions(preferCanvas = TRUE)) %>%
  #   setView(lat = (bbox[2] + bbox[4]) /2, lng = (bbox[1] + bbox[3]) /2, zoom = 14) %>%
  #   addTiles(group = "OSM (default)",
  #            options = providerTileOptions(noWrap = TRUE, minzoom=10, maxZoom=20, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
  #   addProviderTiles(providers$Esri.WorldImagery,
  #                    options = providerTileOptions(noWrap = TRUE, minzoom=10, maxZoom=20, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
  #   addPolygons(data = boundaries,fill = NA, weight = 1, color = "red") %>%
  #   addMarkers(data = points)    
   
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
    plotBoundaries()
  })
  
  geoPoints<- reactive( {
    req(input$borderWidth)
    b <- plotBoundaries()
    p <- st_as_sf(data(), coords = c("Longitude", "Latitude"), 
                  crs = st_crs(b))
    
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
    boundaries <- geoBoundaries()
    bbox <- as.numeric(st_bbox(boundaries))
    leaflet(options = leafletOptions(preferCanvas = TRUE)) %>%
      setView(lat = (bbox[2] + bbox[4]) /2, lng = (bbox[1] + bbox[3]) /2, zoom = 14) %>%
      addTiles(group = "OSM (default)",
               options = providerTileOptions(noWrap = TRUE, minzoom=10, maxZoom=20, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE, minzoom=10, maxZoom=20, updateWhenZooming = FALSE, updateWhenIdle = TRUE)) %>%
      addPolygons(data = boundaries,fill = NA, weight = 1, color = "red") %>%
      addCircleMarkers(data = geoPoints(), weight=1, stroke=FALSE, opacity=1.0, fillColor = "green")
  })

  output$emmap <- renderLeaflet({
    leaflet() %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)") %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE)) %>%
    addPolygons(data = geoBoundaries()) #%>%
    #addMarkers(data = geopoints())    
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
