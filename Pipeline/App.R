library(shiny)
library(dplyr)
library(leaflet)

ui <- fluidPage(
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
                      wellPanel(style = "height: 60vh;",
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


server <- function(input, output, session) {
  data <- reactive({
    req(input$upload)
    ext <- tools::file_ext(input$upload$name)
    if (ext != "csv") { validate("Invalid file; Please upload a .csv file") }
    df <- read.csv(input$upload$datapath, sep = ",", header=T) %>%
      mutate(DateTime = as.POSIXct(paste(YYYY.MM.DD, HH.MM.SS.F),  
                                   format="%d/%m/%Y %H:%M.%S")) %>%
      rename_at(vars(starts_with('EM.')),  ~ sub("^EM\\.", "", .x)) %>%
      select(-c(`YYYY.MM.DD`, `HH.MM.SS.F`), -starts_with("Operator")) %>%
      relocate(DateTime) %>%
      rename_at(vars(ends_with('.2')),  ~ sub("\\.2$", "", .x)) %>%
      select(-c(ends_with('.1')))
  })
  
  uploadPlotBoundaries <- reactive({
    req(input$uploadPlotBoundaries)
    ext <- tools::file_ext(input$uploadPlotBoundaries$name)
    switch(ext,
           kml = read_sf(input$upload$datapath),
           validate("Invalid file; Please upload a .kml file"))
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

  #geopoints<- reactive( {
  #  req(input$borderWidth)
  # #uploadPlotBoundaries()
  #  NULL
  #})
  
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
    leaflet() %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)") %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE))# %>%
      #addMarkers(data = geopoints())    
  })

  output$emmap <- renderLeaflet({
    leaflet() %>%
      setView(lat = -26, lng = 135, zoom = 4) %>%
      addTiles(group = "OSM (default)") %>%
      addProviderTiles(providers$Esri.WorldImagery,
                       options = providerTileOptions(noWrap = TRUE))# %>%
    #addMarkers(data = geopoints())    
  })
  
  output$emHist <- renderPlot({
    ggplot(emScreenedData() ) + 
      geom_histogram(aes(x = .data[[input$emWhat]] ))
  })

  output$emBox <- renderPlot({
    ggplot(emScreenedData() ) + 
      geom_boxplot(aes(y = .data[[input$emWhat]] ))
  })
  
  #observe({
  #  input$reset_button
  #  leafletProxy("geomap") %>% setView(lat = initial_lat, lng = initial_lng, zoom = initial_zoom)
  #})
}

shinyApp(ui, server)
