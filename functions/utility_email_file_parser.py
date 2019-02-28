# -*- coding: utf-8 -*-
# pragma pylint: disable=unused-argument, no-self-use
"""Function implementation"""

import re
import os
import email
import tempfile
import logging
from BeautifulSoup import BeautifulSoup as BSHTML
from email.header import decode_header
from resilient_lib import get_file_attachment
from resilient_circuits import ResilientComponent, function, handler, StatusMessage, FunctionResult, FunctionError
import utilities.util.selftest as selftest

log = logging.getLogger(__name__)

def_self = None
incident_id = None
attachment_id = None
eml_filename = None
attachments = []
urls = []

results = {}  # Contains: body (string), mail_items (list), attachments (list), urls (list)

WEB_URL_REGEX = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""
HTML_URL_REGEX = r'href=[\'"]?([^\'" >]+)'


# This takes RTF formmated text, and returns a clean string of the text.
#   Credit to Markus Jarderot (mizardx.blogspot.com) via stackoverflow.com/a/44580939
# @param text -> [String], The string of RTF text that needs conversion.
# @return -> [String], The cleaned string of text.
def striprtf(text):
    pattern = re.compile(r"\\([a-z]{1,32})(-?\d{1,10})?[ ]?|\\'([0-9a-f]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)", re.I)
    # control words which specify a "destionation".
    destinations = frozenset((
        'aftncn', 'aftnsep', 'aftnsepc', 'annotation', 'atnauthor', 'atndate', 'atnicn', 'atnid',
        'atnparent', 'atnref', 'atntime', 'atrfend', 'atrfstart', 'author', 'background',
        'bkmkend', 'bkmkstart', 'blipuid', 'buptim', 'category', 'colorschememapping',
        'colortbl', 'comment', 'company', 'creatim', 'datafield', 'datastore', 'defchp', 'defpap',
        'do', 'doccomm', 'docvar', 'dptxbxtext', 'ebcend', 'ebcstart', 'factoidname', 'falt',
        'fchars', 'ffdeftext', 'ffentrymcr', 'ffexitmcr', 'ffformat', 'ffhelptext', 'ffl',
        'ffname', 'ffstattext', 'field', 'file', 'filetbl', 'fldinst', 'fldrslt', 'fldtype',
        'fname', 'fontemb', 'fontfile', 'fonttbl', 'footer', 'footerf', 'footerl', 'footerr',
        'footnote', 'formfield', 'ftncn', 'ftnsep', 'ftnsepc', 'g', 'generator', 'gridtbl',
        'header', 'headerf', 'headerl', 'headerr', 'hl', 'hlfr', 'hlinkbase', 'hlloc', 'hlsrc',
        'hsv', 'htmltag', 'info', 'keycode', 'keywords', 'latentstyles', 'lchars', 'levelnumbers',
        'leveltext', 'lfolevel', 'linkval', 'list', 'listlevel', 'listname', 'listoverride',
        'listoverridetable', 'listpicture', 'liststylename', 'listtable', 'listtext',
        'lsdlockedexcept', 'macc', 'maccPr', 'mailmerge', 'maln', 'malnScr', 'manager', 'margPr',
        'mbar', 'mbarPr', 'mbaseJc', 'mbegChr', 'mborderBox', 'mborderBoxPr', 'mbox', 'mboxPr',
        'mchr', 'mcount', 'mctrlPr', 'md', 'mdeg', 'mdegHide', 'mden', 'mdiff', 'mdPr', 'me',
        'mendChr', 'meqArr', 'meqArrPr', 'mf', 'mfName', 'mfPr', 'mfunc', 'mfuncPr', 'mgroupChr',
        'mgroupChrPr', 'mgrow', 'mhideBot', 'mhideLeft', 'mhideRight', 'mhideTop', 'mhtmltag',
        'mlim', 'mlimloc', 'mlimlow', 'mlimlowPr', 'mlimupp', 'mlimuppPr', 'mm', 'mmaddfieldname',
        'mmath', 'mmathPict', 'mmathPr', 'mmaxdist', 'mmc', 'mmcJc', 'mmconnectstr',
        'mmconnectstrdata', 'mmcPr', 'mmcs', 'mmdatasource', 'mmheadersource', 'mmmailsubject',
        'mmodso', 'mmodsofilter', 'mmodsofldmpdata', 'mmodsomappedname', 'mmodsoname',
        'mmodsorecipdata', 'mmodsosort', 'mmodsosrc', 'mmodsotable', 'mmodsoudl',
        'mmodsoudldata', 'mmodsouniquetag', 'mmPr', 'mmquery', 'mmr', 'mnary', 'mnaryPr',
        'mnoBreak', 'mnum', 'mobjDist', 'moMath', 'moMathPara', 'moMathParaPr', 'mopEmu',
        'mphant', 'mphantPr', 'mplcHide', 'mpos', 'mr', 'mrad', 'mradPr', 'mrPr', 'msepChr',
        'mshow', 'mshp', 'msPre', 'msPrePr', 'msSub', 'msSubPr', 'msSubSup', 'msSubSupPr', 'msSup',
        'msSupPr', 'mstrikeBLTR', 'mstrikeH', 'mstrikeTLBR', 'mstrikeV', 'msub', 'msubHide',
        'msup', 'msupHide', 'mtransp', 'mtype', 'mvertJc', 'mvfmf', 'mvfml', 'mvtof', 'mvtol',
        'mzeroAsc', 'mzeroDesc', 'mzeroWid', 'nesttableprops', 'nextfile', 'nonesttables',
        'objalias', 'objclass', 'objdata', 'object', 'objname', 'objsect', 'objtime', 'oldcprops',
        'oldpprops', 'oldsprops', 'oldtprops', 'oleclsid', 'operator', 'panose', 'password',
        'passwordhash', 'pgp', 'pgptbl', 'picprop', 'pict', 'pn', 'pnseclvl', 'pntext', 'pntxta',
        'pntxtb', 'printim', 'private', 'propname', 'protend', 'protstart', 'protusertbl', 'pxe',
        'result', 'revtbl', 'revtim', 'rsidtbl', 'rxe', 'shp', 'shpgrp', 'shpinst',
        'shppict', 'shprslt', 'shptxt', 'sn', 'sp', 'staticval', 'stylesheet', 'subject', 'sv',
        'svb', 'tc', 'template', 'themedata', 'title', 'txe', 'ud', 'upr', 'userprops',
        'wgrffmtfilter', 'windowcaption', 'writereservation', 'writereservhash', 'xe', 'xform',
        'xmlattrname', 'xmlattrvalue', 'xmlclose', 'xmlname', 'xmlnstbl',
        'xmlopen',
    ))
    # Translation of some special characters.
    specialchars = {
        'par': '\n',
        'sect': '\n\n',
        'page': '\n\n',
        'line': '\n',
        'tab': '\t',
        'emdash': '\u2014',
        'endash': '\u2013',
        'emspace': '\u2003',
        'enspace': '\u2002',
        'qmspace': '\u2005',
        'bullet': '\u2022',
        'lquote': '\u2018',
        'rquote': '\u2019',
        'ldblquote': '\201C',
        'rdblquote': '\u201D',
    }

    stack = []
    ignorable = False  # Whether this group (and all inside it) are "ignorable"
    ucskip = 1  # Number of ASCII characters to skip after a unicode character.
    curskip = 0  # Number of ASCII characters left to skip
    out = []  # Output buffer.
    for match in pattern.finditer(text.decode()):
        word, arg, hex, char, brace, tchar = match.groups()
        if brace:
            curskip = 0
            if brace == '{':
                # Push state
                stack.append((ucskip, ignorable))
            elif brace == '}':
                # Pop state
                ucskip, ignorable = stack.pop()
        elif char:  # \x (not a letter)
            curskip = 0
            if char == '~':
                if not ignorable:
                    out.append('\xA0')
            elif char in '{}\\':
                if not ignorable:
                    out.append(char)
            elif char == '*':
                ignorable = True
        elif word:  # \foo
            curskip = 0
            if word in destinations:
                ignorable = True
            elif ignorable:
                pass
            elif word in specialchars:
                out.append(specialchars[word])
            elif word == 'uc':
                ucskip = int(arg)
            elif word == 'u':
                c = int(arg)
                if c < 0: c += 0x10000
                if c > 127:
                    out.append(chr(c))  # NOQA
                else:
                    out.append(chr(c))
                curskip = ucskip
        elif hex:  # \'xx
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                c = int(hex, 16)
                if c > 127:
                    out.append(chr(c))  # NOQA
                else:
                    out.append(chr(c))
        elif tchar:
            if curskip > 0:
                curskip -= 1
            elif not ignorable:
                out.append(tchar)
    return ''.join(out)


# This takes multipart parts of an email and returns the html version, if available
#   Credit to MythRen via gist.github.com/MythRen/25576219140a942824dd37858f0fef68
# @param subparts -> [List of Message Objects], The multipart/alternative payload of a message.
# @return -> [String], The subpart, html if available
def choose_alternative_part(subparts):
    return sorted(subparts, key=lambda m: 1 if m.get_content_subtype() == 'html' else 0, reverse=True)[0]


# Walks an email and returns its parts
#   Credit to MythRen via gist.github.com/MythRen/25576219140a942824dd37858f0fef68
# @param mail -> [List of Message Objects], The multipart/alternative payload of a message.
# @return -> [String], The subpart, html if available
def walk(mail):

    if mail.is_multipart():

        subparts = mail.get_payload()
        content_type = mail.get_content_type()

        if content_type and content_type.lower() == 'multipart/alternative':
            prefer_subpart = choose_alternative_part(subparts)
            for subpart in walk(prefer_subpart):
                yield subpart

        else:
            for subpart in subparts:
                for subsubpart in walk(subpart):
                    yield subsubpart

    else:
        yield mail


# This takes an email's message body, and returns a clean string of the text.
#   Works by decoding the email body using character set detection if the header is not set.
#   Partial credit to miohtama via gist.github.com/miohtama/5389146
# @param mail -> [String], The email message object structure from a string
# @return -> [String], The cleaned email body string of text encoded in UTF-8.
def get_decoded_email_body(mail):

    global def_self
    global incident_id
    global eml_filename
    global attachments
    global urls
    text = ''
    if mail.is_multipart():

        for part in list(walk(mail)):

            try:
                if part is None: continue

                charset = part.get_content_charset()

                if (part.get('Content-Disposition') is not None) and part.get_filename() is not None:  # Apparently, this may also work just as well, untested: if part.is_attachment():
                    if "attachment" in part.get('Content-Disposition').lower():
                        try:
                            filename = part.get_filename()
                            content = part.get_payload(decode=True)
                            text += '[attachment:' + filename + ']'

                            # TO-DO: Save attachment to incident. For reference: open(filename, 'wb').write(content)
                            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                try:
                                    temp_file.write(content)
                                    temp_file.close()
                                    artifact_type_id = 16  # Other File (as default)
                                    def_self.rest_client().post_artifact_file('/incidents/{0}/artifacts/files'.format(incident_id), artifact_type_id, temp_file.name, description='Attachment from {0}'.format(eml_filename), value=filename)
                                    def_self.rest_client().post_attachment('/incidents/{0}/attachments'.format(incident_id), temp_file.name, '[MALICIOUS] {0}'.format(filename))
                                    attachments.append(filename)
                                finally:
                                    os.unlink(temp_file.name)
                        except: pass

                elif part.get_payload(decode=True) is None:
                    continue

                elif part.get_content_charset() is None:
                    # We cannot know the character set, so return decoded "something" ...
                    text += unicode(part.get_payload(decode=True), errors='replace').encode('UTF-8', 'replace').strip()  # Trying this - may decide to remove later. -JJF, 2/23/2019
                    #continue

                elif part.get_content_type() == 'text/plain':
                    t = unicode(part.get_payload(decode=True), str(charset), 'replace').encode('UTF-8', 'replace').strip()
                    text += '<br />'.join(t.splitlines())  # To HTML

                    urls_temp = re.findall(WEB_URL_REGEX, text.strip())
                    for u in urls_temp:
                        if u not in urls: urls.append(u)

                elif part.get_content_type() == 'text/html':
                    t = unicode(part.get_payload(decode=True), str(charset), 'replace').encode('UTF-8', 'replace').strip()
                    text += str(t)

                    skip_image_urls = []
                    urls_html_temp = re.findall(HTML_URL_REGEX, text.strip())
                    # Could also try: [a.get('href') for a in soup.find_all('a', href=True)]
                    soup = BSHTML(text)
                    images = soup.findAll('img')
                    for image in images:
                        skip_image_urls.append(image['src'])
                    for u in urls_html_temp:
                        if (u not in urls) and (u not in skip_image_urls): urls.append(u)


                elif part.get_content_type() == 'text/enriched':  # This has not been tested yet, no test cases available.
                    t = unicode(part.get_payload(decode=True), str(charset), 'replace').encode('UTF-8', 'replace').strip()
                    text += '<br />'.join(striprtf(t).splitlines())  # To HTML

                    urls_temp = re.findall(WEB_URL_REGEX, text.strip())
                    for u in urls_temp:
                        if u not in urls: urls.append(u)

            except Exception as err:
                log.info('[ERROR] Encountered: ' + str(err))  # For debugging unexpected situations, function is robust as-is though

        if text is not None and text is not "":
            return text.strip()

        else:
            return 'Unable to parse email body. Was it empty?'

    else:
        t = unicode(mail.get_payload(decode=True), mail.get_content_charset(), 'replace').encode('UTF-8', 'replace')
        text = '<br />'.join(t.splitlines())  # To HTML

        urls_temp = re.findall(WEB_URL_REGEX, text.strip())
        for u in urls_temp:
            if u not in urls: urls.append(u)

        return text.strip()


class FunctionComponent(ResilientComponent):
    """Component that implements Resilient function 'utility_email_file_parser"""

    def __init__(self, opts):
        """constructor provides access to the configuration options"""
        super(FunctionComponent, self).__init__(opts)
        self.options = opts.get("utilities", {})
        selftest.selftest_function(opts)

    @handler("reload")
    def _reload(self, event, opts):
        """Configuration options have changed, save new values"""
        self.options = opts.get("utilities", {})

    @function("utility_email_file_parser")
    def _utility_email_file_parser_function(self, event, *args, **kwargs):
        """Function: Parses .eml files for email forensics. Useful for reported phishes."""
        try:
            # Get the function parameters:
            global def_self
            global incident_id
            global attachment_id
            global eml_filename
            global attachments
            global urls
            def_self = self
            incident_id = kwargs.get("incident_id")  # number
            attachment_id = kwargs.get("attachment_id")  # number
            eml_filename = kwargs.get("attachment_name")  # text

            eml_file = get_file_attachment(self.rest_client(), incident_id, artifact_id=None, task_id=None, attachment_id=attachment_id)

            yield StatusMessage("Reading and decoding email message...")

            # Parse the email content
            mail = email.message_from_string(eml_file.decode("utf-8"))  # Get the email object from the raw contents
            email_body = get_decoded_email_body(mail)  # Get the UTF-8 encoded body from the raw email string


            results['body'] = str(email_body)
            results['mail_items'] = mail.items()
            results['attachments'] = attachments
            results['urls'] = list(set(urls))  # Ensures no duplicates
            attachments = []
            urls = []

            # Produce a FunctionResult with the results
            yield FunctionResult(results)
        except Exception:
            yield FunctionError()
