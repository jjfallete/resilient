# NOTE: The column must be of type "Text Area" with "Rich Text" set to yes.


# CONFIG:
table_api_name = 'host_network_routing_data'  # The API table name of the table to write the data to
column_api_name = 'network_routing_data'  # The API name of the single column in the table
max_rows_for_table = 5  # The maximum number of rows to write to the table
remove_first_row = False # Remove the first row (if it contains headers AND inputs.csv_fields was used with different field names).


# DYNAMIC CODE:
if remove_first_row is True: rows = (results['json_data'])[1:]
else: rows = results['json_data']

if len(rows) != 0:  # If the CSV contained at least one row
  
  for row in rows:
    
    table_row = incident.addRow(table_api_name)  # Create a row in the data table
    max_rows_for_table = max_rows_for_table - 1  # Decrement max_rows_for_table to indicate max remaining rows to create

    for column_index in range(len(row.values())):  # For each column (property) in the row
    
      row_data_for_column = str(row['content'])  # Get the row's data for the column of the row (cell value)
      table_row[column_api_name] = helper.createRichText('<div><span style="font-family: monospace;">' + str(row_data_for_column).replace(' ', '&emsp;') + '</span></div>')  # Write to the row's proper column (cell)
      
    if max_rows_for_table == 0: break  # Exit once the max_rows_for_table is hit
