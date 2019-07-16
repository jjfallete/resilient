import re

# A script to create an incident from an email message, and add artifacts to the incident based on information
# present in the body text of the message.

for attachment in emailmessage.attachments:
  if not attachment.inline:
    incident.addEmailAttachment(attachment.id)


#  Create basic variables
incident_id = int((emailmessage.subject).split('[Resilient Incident ID# ', 1)[-1].split(']', 1)[0].strip())
email_body = emailmessage.body.content


#  Perform email_body cleaning/sanitization (ensures description field neatness)
email_body_cleaned = ''
email_body_html = email_body
if emailmessage.getBodyHtmlRaw(): email_body_html = emailmessage.getBodyHtmlRaw()  # Attempt to use HTML is available
for line in email_body_html.splitlines(): email_body_cleaned += line.strip()
while '  ' in email_body_cleaned: email_body_cleaned = email_body_cleaned.replace('  ', ' ')
email_body_cleaned = email_body_cleaned.strip().encode('ascii', 'ignore').decode('ascii')
email_subject_cleaned = emailmessage.subject.encode('ascii', 'ignore').decode('ascii')


# Query all Resilient incidents, looking for incidents with the ID
query_builder.equals(fields.incident.id, incident_id)
query = query_builder.build()
incidents = helper.findIncidents(query)

if len(incidents) != 0:
  emailmessage.associateWithIncident(incidents[0])
  
  #if(incident.plan_status == 'A') : old_status = "active"
  #else: old_status = "closed"
  if ('auto-submitted', ['auto-generated']) not in emailmessage.headers.viewitems():  # If not an auto-reply. NOTE: This might vary by org, change as needed.
    note = '''<b><i>Recieved the following email in reference to this incident.</i></b><br/><br/><b><u>Email Sender</u>:</b> {}<br/><b><u>Email Subject</u>:</b> {}<br/><b><u>Email Body</u>:</b><br/><br/>{}'''.format((emailmessage.from)['address'], email_subject_cleaned, email_body_cleaned)
    rich_note = helper.createRichText(note)
    incident.addNote(rich_note)

    incident.plan_status = 'A'  # Ensure incident is opened
    
  else:
    () # Don't do anything if an auto-reply
