##EM Buggy=group
##Boxplot=name
##data=vector
##output_plots_to_html
##X=Field data

library(ggplot2)

# simple boxplot
g <- ggplot(data) +
  geom_boxplot(aes(y=.data[[X]])) + 
  labs() + 
  theme_minimal()

print(g)