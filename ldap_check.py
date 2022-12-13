"""This script will check to see if an End User is ldap enabled or not, and needs to update
their profile with their number so active directory can sync properly. 

Copyright (c) 2022 Cisco and/or its affiliates.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import csv
import os
import sys
from traceback import print_tb
from lxml import etree
from requests import Session
from zeep.cache import SqliteCache
from requests.auth import HTTPBasicAuth
from zeep.plugins import HistoryPlugin
from zeep import Client, Settings, Plugin, xsd
from zeep.transports import Transport
from zeep.exceptions import Fault
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

# Edit .env file to specify your Webex site/user details
from dotenv import load_dotenv
load_dotenv()

# The WSDL is a local file
WSDL_FILE = 'schema/AXLAPI.wsdl'

# Change to true to enable output of request/response headers and XML
DEBUG = False

# If you have a pem file certificate for CUCM, uncomment and define it here

#CERT = 'some.pem'

# These values should work with a DevNet sandbox
# You may need to change them if you are working with your own CUCM server

 
disable_warnings(InsecureRequestWarning)



# This class lets you view the incoming and outgoing http headers and/or XML
class MyLoggingPlugin( Plugin ):

    def egress( self, envelope, http_headers, operation, binding_options ):

        # Format the request body as pretty printed XML
        xml = etree.tostring( envelope, pretty_print = True, encoding = 'unicode')

        print( f'\nRequest\n-------\nHeaders:\n{http_headers}\n\nBody:\n{xml}' )

    def ingress( self, envelope, http_headers, operation ):

        # Format the response body as pretty printed XML
        xml = etree.tostring( envelope, pretty_print = True, encoding = 'unicode')

        print( f'\nResponse\n-------\nHeaders:\n{http_headers}\n\nBody:\n{xml}' )

session = Session()

# We avoid certificate verification by default, but you can uncomment and set
# your certificate here, and comment out the False setting

#session.verify = CERT
session.verify = False
session.auth = HTTPBasicAuth( os.getenv( 'AXL_USERNAME' ), os.getenv( 'AXL_PASSWORD' ) )

# Create a Zeep transport and set a reasonable timeout value
transport = Transport( session = session, timeout = 10 )

# strict=False is not always necessary, but it allows zeep to parse imperfect XML
settings = Settings( strict=False, xml_huge_tree=True )

# If debug output is requested, add the MyLoggingPlugin callback
plugin = [ MyLoggingPlugin() ] if DEBUG else [ ]

# Create the Zeep client with the specified settings
client = Client( WSDL_FILE, settings = settings, transport = transport,
        plugins = plugin )
history = HistoryPlugin()
# service = client.create_service("{http://www.cisco.com/AXLAPIService/}AXLAPIBinding", CUCM_URL)
service = client.create_service( '{http://www.cisco.com/AXLAPIService/}AXLAPIBinding',
                                f'https://{os.getenv( "CUCM_ADDRESS" )}:8443/axl/' )

#should output any errors coming from cucm while interacting with the program
def show_history():
     for hist in [history.last_sent, history.last_received]:
         print(etree.tostring(hist["envelope"], encoding='unicode', pretty_print=True))


filename = 'agent list.csv'
with open(filename, 'r') as csvfile:
    datareader = csv.reader(csvfile)
    for row in datareader:
        enumber = row[0].capitalize()
        try:
            resp = service.getUser(userid=enumber)
            ldap_status = resp['return']['user']['ldapDirectoryName']['_value_1']
            first_name = resp['return']['user']['firstName']
            last_name = resp['return']['user']['lastName']
            if ldap_status == 'Memorial Hermann Directory Sync':
                print(first_name + " " + last_name + " " + enumber + " is in Workday and is LDAP enabled.")
            else:
                print(first_name + " " + last_name + " " + enumber + " needs to update Workday.")

        except Fault:
            print("No End User found for " + enumber)
            show_history()
