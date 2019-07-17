# NOTE: Ensure the Resilient data table's column names are the same as the results['fieldnames'] fields returned (order does not matter).
#           This means that, for example, "Username" from the fields cannot be "User Name" or "User" in the data table.


# CONFIG:
table_api_name = 'host_prefetch_files'  # The API table name of the table to write the data to
max_rows_for_table = 200  # The maximum number of rows to write to the table
remove_first_row = True # Remove the first row (if it contains headers AND inputs.csv_fields was used with different field names).


# DYNAMIC CODE:
if remove_first_row is True: rows = (results['json_data'])[1:]
else: rows = results['json_data']

if len(rows) != 0:  # If the CSV contained at least one row
  
  column_labels = results['fieldnames']  # column_labels = results['json_data'][0].keys()
  
  for row in rows:
    table_row = incident.addRow(table_api_name)  # Create a row in the data table
    max_rows_for_table = max_rows_for_table - 1  # Decrement max_rows_for_table to indicate max remaining rows to create

    for column_index in range(len(row)):  # For each column (property) in the row
    
      column_api_name = str(column_labels[column_index]).lower().replace(' ', '_').replace('-', '').strip()  # Convert the column label to the table's API column name
      row_data_for_column = str(row[column_labels[column_index]])  # Get the row's data for the column of the row (cell value)
      
      table_row[column_api_name] = row_data_for_column  # Write to the row's proper column (cell)
      
    if max_rows_for_table == 0: break  # Exit once the max_rows_for_table is hit
    
