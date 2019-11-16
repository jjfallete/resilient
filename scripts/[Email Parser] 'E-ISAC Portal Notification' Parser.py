"""
@Title: 'E-ISAC Portal Notification' Parser
@Purpose: Parses 'E-ISAC Portal Notification' emails sent from E-ISAC.
@Author: Jared Fagel, et al. as mentioned.
@Date: 02/12/2019 - Modified: 02/15/2019
"""

import re
import java.util.Date as Date


###  Create basic variables [START]
incident_owner = "alerts_resilient@allete.com"
email_subject_line = emailmessage.subject
email_body = emailmessage.body.content
email_sender_email_address = (emailmessage.from)['address']
email_recipient_email_address = (emailmessage.to)[0]['address']
###  Create basic variables [END]


###  Perform email_body cleaning/sanitization (ensures fields look neat) [START]
email_body_html = email_body
email_body_cleaned = ''

if emailmessage.getBodyHtmlRaw():
  email_body_html = emailmessage.getBodyHtmlRaw()  # Attempt to use HTML if available
  
for line in email_body_html.splitlines():
  email_body_cleaned += line.strip()
  
while '  ' in email_body_cleaned:
  email_body_cleaned = email_body_cleaned.replace('  ', ' ')
  
email_body_cleaned = email_body_cleaned.strip()
email_body = email_body.replace('\n', ' ').replace('\r', ' ')
###  Perform email_body cleaning/sanitization (ensures fields look neat) [END]


###  Parse items from email_body [START]
bulletin_name = 'E-ISAC Portal Notification - ' + ((email_subject_line.split('E-ISAC Portal Notification - ', 1)[1]).split(' - New Cyber Bulletin', 1)[0]).strip()
#bulletin_name = bulletin_name.encode('ascii', 'ignore').decode('ascii', 'ignore')
bulletin_description = ((email_body_cleaned.split('Cyber Bulletin Follows', 1)[1]).split('To login and view the entire posting, click here:', 1)[0]).strip()
bulletin_description = bulletin_description[::-1].replace('<br>'[::-1], ''[::-1], 2)[::-1]
bulletin_description = bulletin_description.replace('style=', 'strip=').replace('<span', '<remove_me', 1).replace('</p><p>', '<br><br>').replace('</span>', '', 1).replace('<br', '<xyz', 1) #  Formatting for neatness

try: 
  eisac_url = ((email_body.split('To login and view the entire posting, click here:', 1)[1]).split('For more information', 1)[0]).replace('<','').replace('>','').replace('https://', '', 1).strip().lower().splitlines()[0]
  if 'https://' in eisac_url and 'sendgrid.net/' in eisac_url: eisac_url = 'https://' + eisac_url.split('https://', 1)[0]  # Correct sendgrid URLs
  else: eisac_url = 'https://' + eisac_url
  bulletin_identifier = int(eisac_url.split('id=', 1)[1].strip())
except: 
  eisac_url = 'N/A'
  bulletin_identifier = int(email_subject_line.rsplit(' [ID ', 1)[1].rsplit(',', 1)[0].strip())
 ###  Parse items from email_body [END]   


###  Create or merge the bulletin into an incident [START]

# Query all Resilient incidents, looking for incidents with the same bulletin_name and bulletin_identifier (already created)
query_builder.equals(fields.incident.bulletin_id, bulletin_identifier)
query = query_builder.build()
incidents = helper.findIncidents(query)

# The incident already exists. Associate the bulletin update with the pre-existing incident.
if (len(incidents) != 0) and (' - Modified ' in email_subject_line):
  emailmessage.associateWithIncident(incidents[0])
  
  if(incident.plan_status == 'A') : old_status = "active"
  else: old_status = "closed"
  
  incident.addNote('An update to this bulletin was made. This incident was ' + old_status + ' prior.')
  incident.plan_status = 'A'
  
# Otherwise, create the new incident.
else:
  emailmessage.createAssociatedIncident(bulletin_name, incident_owner)
  timestamp = ((email_body.replace(bulletin_name.strip('E-ISAC Portal Notification - '), '').split('TLP: ', 1)[0]).strip().split(' on ', 1)[1]).strip()
  
  tlp = ((email_body.split('TLP: ', 1)[1]).split('Category: ', 1)[0]).strip().lower()
  if('white' in tlp): tlp = 'TLP:White (everyone)'
  if('green' in tlp): tlp = 'TLP:Green (community)'
  if('amber' in tlp): tlp = 'TLP:Amber (organization)'
  if('red' in tlp): tlp = 'TLP:Red (restricted)'
  
  urgency = 'N/A'
  try: urgency = ((email_body.split('Urgency: ', 1)[1]).split(' ', 1)[0]).strip()
  except: pass

  # Remove all tables -- Resilient's RTE does not support tables.
  while('<table' in bulletin_description):
    html_table = '<table' + ((bulletin_description.split('<table', 1)[1]).split('table>', 1)[0]) + 'table>'
    bulletin_description = bulletin_description.replace(html_table, '<b><i>[ HTML data table removed by Resilient - Check E-ISAC Website ]</i></b>').strip() + '<br /><br />'
  
  #  Set incident fields
  incident.description = helper.createRichText(bulletin_description)
  incident.incident_type_ids = ['[Informational] Other']
  incident.source = 'E-ISAC'
  incident.sensitivity = tlp
  incident.severity_code = 'Normal'
  incident.csirt_level = '0 - No impact to corporate systems.'
  incident.start_date = Date().parse(timestamp)
  incident.source_url_safe = '<a href="' + eisac_url + '">' + eisac_url + '</a>'
  incident.bulletin_id = bulletin_identifier
  
  incident.email_source_type = 'E-ISAC Portal Notification'
  incident.email_subject = email_subject_line
  incident.sender_email_address = email_sender_email_address
  incident.recipient_email_address = email_recipient_email_address
  ###  Create or merge the bulletin into an incident [END]
