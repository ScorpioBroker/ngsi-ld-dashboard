# City Livability Index Flexible Frontend CLIFF

## Introduction
A dashboard for ngsi-ld applications with a map visualization of geoproperties and temporal evolution views of the data

#### 📝 Description
The flexible frontend provides a general visualization of NGSI-LD Entities, their historical evolution and relationships. The flexible frontend can be configured to execute multiple NGSI-LD queries and visualizes the resulting Entities on a map if a location is provided. Additionally a specific attribute needs to be provided to apply a color scale to the resulting geometries on the map.

This flexibility allows us to use the flexible frontend not only for CLIFF but also for the Sentiment analysis. 
For the City Livability Index we provide a set of predefined queries retrieving the indexes calculated. Calculated indexes contain NGSI-LD Relationships which transparently allow stake holders to understand the indexes. The flexible frontend provides an intuitive visualization of these relationships, which the end user can directly follow and retrieve more detail information on the linked entity. 

Additionally the flexible frontend provides visualizations for the historical evolution for a selected entity or index. Furthermore aggregated data over a timeframe is visualized. The flexible frontend provides, if applicable, average, minimum, maximum, sum and standard deviation. 

Since certain data, such as text or complex data, cannot be visualized in a graph we provide a table overview as a fallback solution. 
For easier access, the historical evolution is also available for individual attributes of an entity.

#### 🏆 Value Proposition

The flexible frontend provides a configurable visualization for various scenarios. In SALTED we used already twice to visualize use cases. It can also be used outside of the scope of SALTED by anyone who is using NGSI-LD

#### 📧 Contact Information

This component is maintained at https://github.com/ScorpioBroker/ngsi-ld-dashboard please use issue reports there.