The qradar_search function is much different than in the Resilient version (v2.x). This version requires the raw AQL be passed into the function as a string and also allows a query timeout in minutes value as a paramater. The function now also returns a dictionary of the events to the post processor in addition to writing a CSV file as an attachment. This is useful for creating in-product tables of the results within the post-processor (use SELECT inside the AQL). It also has workflow state tracking, and will cancel the search in QRadar upon early termination.


Example Pre-processor:
```
inputs.incident_id = incident.id

# AQL query
query = '''
        SELECT DATEFORMAT(deviceTime, 'MM-dd-yyyy h:mm:ss a z') AS 'Source Time', "URL" AS 'URL', userName AS 'Username', sourceip AS 'Source IP', destinationip AS 'Destination IP'
        FROM events 
        WHERE (logSourceId='1234')
        ORDER BY deviceTime DESC
        LAST qradar_days_goes_here DAYS
        '''
        
query = query.replace('qradar_days_goes_here', str(rule.properties.days_to_search)).strip()  # Replace AQL variables user provided value
inputs.qradar_query = query

inputs.qradar_query_range_start = 0  # Start with the most recent event
inputs.qradar_query_range_end = 1000000  # Limt to 1M events (applies to CSV)
inputs.qradar_query_timeout_mins = rule.properties.qradar_query_timeout_mins  # Timeout before the query search will halt and return what it found
```

Example Post-processor:
```
# NOTE: Ensure the Resilient data table's columns are the same as the AQL fields returned (order does not matter).
#           This means that, for example, "Username" from QRadar AQL cannot be "User Name" or "User" in the data table.

# CONFIG:
table_api_name = 'qradar_url_visits'  # The API table name of the table where events will be added as rows
max_rows_for_table = 200  # The maximum number of rows (events) to write to the table

# DYNAMIC CODE:
if(results['was_successful'] is True):
  if len(results['events']) != 0:  # If there were events returned from the query, we'll add rows to the table
    
    column_labels = results['events'][0].keys()  # Dynamic representation of column labels from QRadar query results
    
    for row in results['events']:  # For each row in the QRadar query results
    
      table_row = incident.addRow(table_api_name)  # Create a row in the data table
      max_rows_for_table = max_rows_for_table - 1  # Decrement max_rows_for_table to indicate max remaining rows (events) to create
      
      for column_index in range(len(row)):  # For each column (property) in the row
        
        column_api_name = str(column_labels[column_index]).lower().replace(' ', '_').strip()  # Convert the column label to the table's API column name
        row_data_for_column = str(row[column_labels[column_index]])  # Get the row's data for the column of the row (cell value)
        
        if 'DC\=com/' in row_data_for_column: row_data_for_column = row_data_for_column.split('DC\=com/', 1)[1]  # Strip DC username junk from it if present
        
        table_row[column_api_name] = row_data_for_column  # Write to the row's proper column (cell)
        
      if max_rows_for_table == 0: break  # Exit once the max_rows_for_table is hit
```

==

The `custromize.py` script is not complete.

To install in "development mode" (recommended)

    pip install -e ./qradar/

After installation, the package will be loaded by `resilient-circuits run`.


To uninstall,

    pip uninstall qradar
