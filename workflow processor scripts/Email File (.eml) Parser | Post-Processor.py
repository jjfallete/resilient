# NOTE: This post-processor contains some custom incident fields and artifact types.
#           Reference for Email headers in MIME: https://tools.ietf.org/html/rfc4021#page-17

import re


# Define variables for artifacts and/or fields
urls = []
source_ip = None
source_country = None
traced_route = ''
message_id = None # Current message_id
list_of_message_ids = []
in_reply_to = [] # Reply-to message_id(s)
references = [] # All message_ids involved
return_address = None
reply_to_address = None
reply_to_name = None
to_list = []
cc_list = []
from_address = None
from_name = None
subject = incident.email_subject
sent_timestamp = None
received_timestamp = None
header = ''


# Get each header element and it's value
for item, content in results.header:  #results.mail_items:
  
  if item.lower() == 'received' or item.lower() == 'received-spf': 
    traced_route += (item + ': ' + content.strip().replace('\r', '') + '\n\n')
 
  elif item.lower() == 'message-id':
    message_id = content.lower()
    
  elif (item.lower() == 'references') or (item.lower() == 'in-reply-to') or (item.lower() == 'original-message-id'):
    temp_list_of_message_ids = list(filter(None, content.replace('<', '').replace(' ', '').split('>')))
    for mid in temp_list_of_message_ids:
      if mid not in list_of_message_ids and mid is not None:
        list_of_message_ids.append(mid)
  
  elif item.lower() == 'return-path':
    if '@' not in content and '<' in content and '>' in content: return_address = content.split('>')[0].split('<')[-1]
    else: return_address = (content.split('@')[0].split('<')[-1] + '@' + content.split('@')[-1].split('>')[0]).replace('"', '').replace("'", '')  # content.rsplit(' ')[-1].replace('<', '').replace('>', '')
    
  elif item.lower() == 'reply-to':
    if '@' not in content and '<' in content and '>' in content: reply_to_address = content.split('>')[0].split('<')[-1]
    else: reply_to_address = (content.split('@')[0].split('<')[-1] + '@' + content.split('@')[-1].split('>')[0]).replace('"', '').replace("'", '')
    try: reply_to_name = content.replace("'", '"').split('"')[1].split('"')[-1]  # content.rsplit(' ')[-1].replace('<', '').replace('>', '')
    except: reply_to_name = reply_to_address
   
  elif item.lower() == 'cc':
    for cc in content.split(','):
      if '@' not in content and '<' in content and '>' in content: cc_address = content.split('>')[0].split('<')[-1]
      else: cc_address = ((cc.split('@')[0].split('<')[-1] + '@' + cc.split('@')[-1].split('>')[0]).replace('"', '').replace("'", ''))
      try: cc_name = cc.split('"')[1].split('"')[-1]
      except: cc_name = cc_address
      cc_list.append([cc_address, cc_name])
    
  elif item.lower() == 'to':
    for to in content.split(','):
      if '@' not in content and '<' in content and '>' in content: to_address = content.split('>')[0].split('<')[-1]
      else: to_address = ((to.split('@')[0].split('<')[-1] + '@' + to.split('@')[-1].split('>')[0]).replace('"', '').replace("'", ''))
      try: to_name = to.split('"')[1].split('"')[-1]
      except: to_name = to_address
      to_list.append([to_address, to_name])

  elif item.lower() == 'from':
    if '@' not in content and '<' in content and '>' in content: from_address = content.split('>')[0].split('<')[-1]
    else: from_address = (content.split('@')[0].split('<')[-1] + '@' + content.split('@')[-1].split('>')[0]).replace('"', '').replace("'", '')
    try: from_name = content.replace("'", '"').split('"')[1].split('"')[-1]  # content.rsplit(' ')[-1].replace('<', '').replace('>', '')
    except: from_name = from_address

  elif item.lower() == 'subject':
    subject = content.strip()

  elif item.lower() == 'date':
    sent_timestamp = content
    
  # Add more here as desired ...
    
  header += (item + ': ' + content.strip().replace('\r', '') + '\n')
    

# Clean returned HTML for rich-text description
email_body_cleaned = ''
email_body = (results.body).strip()
# Protect analyst from email URLs. -JJF 3/11/2019. Disabled 3/12/2019 -- Resilient kills links that are modified with [.] and hxxp
#for url in results.urls:
#  email_body = email_body.replace(url, url.replace('https:', 'hxxps:')).replace(url, url.replace('http:', 'hxxp:'))
for line in email_body.splitlines():
  line = line.replace('<a ', ' <a ')
  while '  ' in line: line = line.replace('  ', ' ')
  email_body_cleaned += (line)
  
email_body_cleaned = helper.createRichText(email_body_cleaned.strip())


# Set incident fields
if email_body_cleaned: incident.description = email_body_cleaned
if subject: incident.email_subject = subject
if from_address: incident.sender_email_address = from_address
if from_name: incident.sender_name = from_name
if to_list: 
  incident.recipient_email_address = str(', '.join(str(to_address) for to_address in [to[0] for to in to_list]))
  incident.recipient_name = str(', '.join(str(to_name) for to_name in [to[1] for to in to_list]))
if cc_list:
  incident.cc_recipient_email_address = str(', '.join(str(cc_address) for cc_address in [cc[0] for cc in cc_list]))
  incident.cc_recipient_name = str(', '.join(str(cc_name) for cc_name in [cc[1] for cc in cc_list]))
if reply_to_address: incident.replyto_email_address = reply_to_address
if reply_to_name: incident.replyto_name = reply_to_name
if return_address: incident.return_email_address = return_address
if source_ip: incident.source_country_code = source_country + ' (' + str(source_ip) + ')'
if header: incident.email_header = helper.createPlainText(header)
if traced_route: incident.email_traced_route = helper.createPlainText(traced_route)
# TO-DO: sent_timestamp and received_timestamp as fields


if source_ip: incident.addArtifact('IP Address', source_ip, 'Source IP address of originating email server')
if return_address: incident.addArtifact('email_return_address', return_address, 'Email address for returned mail')
if reply_to_address: incident.addArtifact('email_replyto_address', reply_to_address, 'Email address of reply-to')
if reply_to_name: incident.addArtifact('email_replyto_name', reply_to_name, 'Name of reply-to')
for to_address, to_name in to_list:
  incident.addArtifact('Email Recipient', to_address, 'Email address of recipient')
  incident.addArtifact('email_recipient_name', to_name, 'Name of recipient (' + to_address + ')')
for cc_address, cc_name in cc_list:
  incident.addArtifact('email_cc_recipient_address', cc_address, 'Email address of carbon copied recipient')
  incident.addArtifact('email_cc_recipient_name', cc_name, 'Name of carbon copied recipient (' + cc_address + ')')

if from_address: incident.addArtifact('Email Sender', from_address, 'Email address of sender')
if from_name: incident.addArtifact('Email Sender Name', from_name, 'Name of email sender')
if subject: incident.addArtifact('Email Subject', subject, 'Subject line of email')
if sent_timestamp: incident.addArtifact('email_sent_timestamp', sent_timestamp, 'The date and time the email was sent by the sender')
if message_id: incident.addArtifact('email_message_id', message_id, 'The current email message identifier')
for mid in list_of_message_ids: incident.addArtifact('email_referenced_message_id', mid, 'A referenced email message identifier of the current email')

if incident.properties['reporter_email_address']:  # TO-DO: If the email BCC'd the reporter, add them as a recipient -- perhaps we want to do this even if CC'd too? TBD.
  if (not any(incident.properties['reporter_email_address'] == addresses[0] for addresses in to_list) and (not any(incident.properties['reporter_email_address'] == addresses[0] for addresses in cc_list))):
    incident.addArtifact('Email Recipient', incident.properties['reporter_email_address'], 'Email address of reporter')
    incident.addArtifact('email_recipient_name', incident.properties['reporter_name'], 'Name of reporter (' + incident.properties['reporter_email_address'] + ')')

for url in results.urls: # Problem-- this gets all URLs (except img URLs), even from possible HTML comments and styling. Solution = run function again, but only for URL adds?
  pattern = re.compile("(http|https|file|gopher|ftp):\\/\\/[^\\s]+")
  if pattern.match(url): incident.addArtifact('URL', url, 'URL from email body')
  # elif url.rstrip() != '': incident.addArtifact('domain', url.rstrip(), 'URL from email body')  # This usually isn't needed
