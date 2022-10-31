"""This is a script to migrate a contact center agent from CIPC to Jabber. AXL fetches the extension mobility 
device profile for a user, copies its settings. Then adds CSF Jabber Device to the enduser which is assigned 
as Owner User ID to that device profile and enables IM and Presence for that End User, using the zeep 
library. Then associates the CSF with pguser and zoomjtapi application user.

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


#ask admin for the e# needed, and format it into needed vars
enumber = input("Enter E# :")
owner_user_name = enumber.capitalize()
deviceprofile = enumber.capitalize() + '_EM_8841'

#retrieve device profile
try:
     resp = service.getDeviceProfile(name=deviceprofile)
except Fault:
    deviceprofile = enumber.capitalize() + '_EM_8851'

try:
     resp = service.getDeviceProfile(name=deviceprofile)
except Fault:
    print("No EM Profile Found")
    sys.exit(1)
    show_history()

#save device profile settings to vars
phone_list = resp['return'].deviceProfile
description = phone_list['description']
lines = phone_list.lines
extension1 = phone_list.lines.line[0]['dirn']['pattern']
phone_pattern = extension1
phone_partition = phone_list.lines.line[0]['dirn']['routePartitionName']['_value_1']
phone_caller_id = phone_list.lines.line[0]['e164Mask']
phone_busy_trigger = phone_list.lines.line[0]['busyTrigger']
uuid1 = phone_list.lines.line[0]['uuid']
device_name = "CSF" + enumber.capitalize()

#create csf template
def fill_phone_info(name, product, owner_user_name, pattern, partition, caller_id, busy_trigger):
    phone_info = {
        'name': name,
        'product': product,
        'model': product,
        'description': f'{description}',
        'class': 'Phone',
        'protocol': 'SIP',
        'protocolSide': 'User',
        'devicePoolName': 'Default',
        'locationName': 'Hub_None',
        'sipProfileName': 'Standard SIP Profile',
        'commonPhoneConfigName': xsd.SkipValue,
        'phoneTemplateName': xsd.SkipValue,
        'primaryPhoneName': xsd.SkipValue,
        'useTrustedRelayPoint': xsd.SkipValue,
        'builtInBridgeStatus': 'On',
        'packetCaptureMode': xsd.SkipValue,
        'certificateOperation': xsd.SkipValue,
        'deviceMobilityMode': xsd.SkipValue,
        'ownerUserName': owner_user_name,
        'lines': lines
    }
    return phone_info


print("\n")
print("-" * 10)
print("Creating " + device_name)
print("-" * 10)
print("\n")


#create csf from device profile

associated_devices = device_name
new_phone = fill_phone_info(device_name, 'Cisco Unified Client Services Framework'\
                ,owner_user_name, phone_pattern, phone_partition, phone_caller_id, phone_busy_trigger)
resp = service.addPhone(new_phone)

print("\n")
print("-" * 10)
print("Updating EndUser")
print("-" * 10)
print("\n")

#update end user and app users
resp = service.updateUser(userid=owner_user_name, associatedDevices=associated_devices, imAndPresenceEnable=False)

print("\n")
print("-" * 10)
print("Updating pguser")
print("-" * 10)
print("\n")

resp = service.getAppUser(userid='pguser')
pguser_device_List = resp['return'].appUser.associatedDevices.device
complete_pguser_list = pguser_device_List + [device_name]

print("\n")
print("-" * 10)
print("Updating zoomjtapi user")
print("-" * 10)
print("\n")

resp = service.getAppUser(userid='zoomjtapi')
zoomjtapi_device_List = resp['return'].appUser.associatedDevices.device
complete_zoomjtapi_list = zoomjtapi_device_List + [device_name]

print("\n")
print("-" * 10)
print("Deleting " + phone_list['name'] + " and associated users CIPC " + enumber)
print("-" * 10)
print("\n")

try:
    rp_resp = service.removePhone( name = enumber)
except:
    device_id = input("Couldn't find the phone with the name of " + enumber + ", try the PC/Device id:").capitalize()

try:
    rp_resp = service.removePhone( name = device_id)
except Fault as err:
    print( f'Zeep error: removePhone: { err }' )

print( '\nremovePhone response:' )
print( rp_resp, '\n' )

try:
    rdp_resp = service.removeDeviceProfile( name = deviceprofile)
except Fault as err:
    print( f'Zeep error: removePhone: { err }' )


print( '\nremovePhone response:' )
print( rdp_resp, '\n' )

