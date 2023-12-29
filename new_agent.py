"""This is a script to migrate a contact center agent from CIPC to Jabber. After being prompted for the username, 
AXL fetches the extension mobility device profile for a user, copies its settings. Then creates a CSF Jabber 
Device for the enduser and associates the new device to the end user. Then it associates the CSF with pguser 
and zoomjtapi application user. Finally, it cleans up and deletes the old CIPC and Device Profile.

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
from itertools import cycle
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

enumber = input("Enter E# :")

#workday search and local end user check to verify AD status

local_end_user = False
LDAP_enabled = False

try:
    resp = service.getUser(userid=enumber)
    ldap_status = resp['return']['user']['ldapDirectoryName']['_value_1']
    first_name = resp['return']['user']['firstName']
    last_name = resp['return']['user']['lastName']
    if ldap_status == None:
        print(first_name + " " + last_name + " " + enumber + " needs to update Workday.")
        answer = input("Are you sure you want to continue? y/n:")
        while True:
            if answer.lower()  in ['yes', 'y']:
                local_end_user = True
                break
            elif answer.lower() in ['no', 'n']:
                sys.exit(1)
            else:
                sys.exit(1)
    else:
        LDAP_enabled = True
        end_user_callerID = resp['return']['user']['telephoneNumber']
        if '-' in end_user_callerID:
            end_user_callerID = input('The caller ID has invalid characters in it, please enter it manually: ')
        print(first_name + " " + last_name + " " + enumber + " is in Workday and is LDAP enabled.")
except Fault:
        print("No End User found for " + enumber)
        show_history()


#retrieve list of all device pools from cucm.
#if user input is blank, try to use the soft phone settings.
#if exact match for dp is found in the list gathered, use that
#otherwise try to find a match in the list and give user a list to chose from

call_center = input("Enter Cost Center or Device Pool to use for " + enumber + ":")

search_again = True
search_successful = False

try:
    if call_center == "":
        print("No DP given, resorting to CIPC settings.")
    else:
        device_pool_list = service.listDevicePool(searchCriteria = { 'name': '%' }, returnedTags = { 'name': ''})
        device_pool_list_names = device_pool_list['return']['devicePool']
        try:
            for dp_index_num, dp_data in enumerate(device_pool_list_names):
                if call_center == dp_data['name']:
                    print('Found Device Pool match ' + dp_data['name'])
                    dp_search_result = dp_data['name']
                    search_again = False
                    search_successful = True
        except:
            print('The search failed.')
        if search_again == True:
            for dp_index_num, dp_data in enumerate(device_pool_list_names):
                if call_center in dp_data['name']:
                    print(dp_index_num, ': Found DPs for Call Center ' + dp_data['name'])
                    search_successful = True
                    #dp = dp_data['name']
            if search_successful == True:
                dp_selection = input('Select the number of the Device Pool you most desire: ')
                dp_search_result = device_pool_list_names[int(dp_selection)]['name']
            else:
                print('There was no Call Center or DP found. Will try to copy Device Settings.')
except Fault:
        print("Something weird happened, I couldn't look for " + call_center)
        show_history()

#start searching for an open extension to assign to the agent, starting at 121605300
try:
    new_agent_dn_list_raw = service.listLine(searchCriteria = {'pattern': '1216053%'}, returnedTags = { 'pattern': '' })
    new_agent_dn_list = new_agent_dn_list_raw['return']['line']
except:
    print('no extensions found')

#distill the list and find the last used extension and identify the next 
agent_DNs = []
for dn_indx, dn_data in enumerate(new_agent_dn_list):
    if dn_data['pattern'][0:4] == '1216':
         agent_DNs.append(dn_data['pattern'])
agent_DNs.sort()
new_agent_pri_dn = (int(agent_DNs[-1]) + 1)
print(str(new_agent_pri_dn))
agent_description = first_name + " " + last_name + " " + str(new_agent_pri_dn)

#create a simple line template first 
primary_line = {
    'pattern': new_agent_pri_dn,
    'description': agent_description,
    'usage': 'Device',
    'routePartitionName': 'PCCE_DN_PT',
    'voiceMailProfileName': 'NoVoiceMail'
}

# Execute the addLine request for primary line because the cucm api is limited and bad
try:
    resp = service.addLine( primary_line )
except Fault as err:
    print( f'Zeep error: addLine: { err }' )
    sys.exit( 1 )

primary_line_uuid = resp['return']
owner_user_name = enumber.capitalize()
device_name = "CSF" + enumber.capitalize()
single_line = True
double_line = False

#a catch if there is a local user to set the caller ID on the line
if local_end_user == True:
    end_user_callerID = input('Enter the External Mask/Caller ID for the Agent: ')
    while len(end_user_callerID) < 9:
        print('Make sure Caller ID is at least 10 digits.')
        end_user_callerID = input('Enter the External Mask/Caller ID for the Agent: ')

#copy from csf, and check if the csf has two lines or not. if the line is a DID, alert the user. if it's an agent line, create a new agent line
csf_example_input = input("If you'd like to copy localization settings from another Agent's CSF, please enter it here, otherwise hit enter: ").upper()
if csf_example_input == '':
    DP_from_CSF = 'Default'
    Location = 'Hub_None'
    MRLN = 'MC_MRGL'
    CSS = '06_Device'
    single_line = True
else:
    try:
        phone_resp = service.getPhone(name=csf_example_input)
        example_line_resp = phone_resp['return']['phone']['lines']['line']
        for ex_line_index, ex_line_data in enumerate(example_line_resp):
            if 2 == ex_line_data['index']:
                double_line = True
                single_line = False
        DP_from_CSF = phone_resp['return']['phone']['devicePoolName']['_value_1']
        Location = phone_resp['return']['phone']['locationName']
        MRLN = phone_resp['return']['phone']['mediaResourceListName']['_value_1']
        CSS = phone_resp['return']['phone']['callingSearchSpaceName']
    except:
        device_id = input("Couldn't find the phone with the name of " + csf_example_input + ", try again:").upper()
        try:
            phone_resp = service.listPhone(searchCriteria = { 'name': device_id }, returnedTags = { 'locationName': '', 'mediaResourceListName': '', 'callingSearchSpaceName': ''})
            if device_id != '':
                DP_from_CSF = phone_resp['return']['phone'][0]['devicePoolName']['_value_1']
                Location = phone_resp['return']['phone'][0]['locationName']
                MRLN = phone_resp['return']['phone'][0]['mediaResourceListName']['_value_1']
                CSS = phone_resp['return']['phone'][0]['callingSearchSpaceName']
            else:
                DP_from_CSF = 'Default'
                Location = 'Hub_None'
                MRLN = 'MC_MRGL'
                CSS = '06_Device'
        except Fault as err:
            print( f'Zeep error: listPhone: { err }' )

#set correct device pool. entering a DP will take precedence over copying from a CSF
if search_successful == True:
    dp = dp_search_result
else:
    dp = DP_from_CSF

#check if the CSF should get two lines or just one. there are templates for a single line and double lines.
if double_line == True:
    if example_line_resp[1]['dirn']['pattern'][0:3] != '121':
        print("This phone will need a DID assigned to it for it's second line.")
        single_line = True
    else:
        new_agent_sec_dn = (new_agent_pri_dn + 1000)
        print(new_agent_sec_dn)
        secondary_line = {
            'pattern': new_agent_sec_dn,
            'description': agent_description,
            'usage': 'Device',
            'routePartitionName': 'PCCE_DN_PT',
            'voiceMailProfileName': 'NoVoiceMail'
        }
        # Execute the addLine request for secondary line because the cucm api is limited and bad
        try:
            sec_resp = service.addLine( secondary_line )
        except Fault as err:
            print( f'Zeep error: addLine: { err }' )
            sys.exit( 1 )

        secondary_line_uuid = sec_resp['return']
        line = {
                    'line': [
                        {
                            'index': 1,
                            'label': agent_description,
                            'display': agent_description,
                            'dirn': {
                                'pattern': new_agent_pri_dn,
                                'routePartitionName': {
                                    '_value_1': 'PCCE_DN_PT',
                                    'uuid': '{56339E9D-FD62-199F-552F-0E4DE058FD2A}'
                                },
                                'uuid': primary_line_uuid
                            },
                            'ringSetting': 'Use System Default',
                            'consecutiveRingSetting': 'Use System Default',
                            'ringSettingIdlePickupAlert': 'Use System Default',
                            'ringSettingActivePickupAlert': 'Use System Default',
                            'displayAscii': agent_description,
                            'e164Mask': end_user_callerID,
                            'dialPlanWizardId': None,
                            'mwlPolicy': 'Use System Policy',
                            'maxNumCalls': 2,
                            'busyTrigger': 1,
                            'callInfoDisplay': {
                                'callerName': 'true',
                                'callerNumber': 'false',
                                'redirectedNumber': 'false',
                                'dialedNumber': 'true'
                            },
                            'recordingProfileName': {
                                '_value_1': 'ZoomCallRec',
                                'uuid': 'e0166dbe-918d-3753-0c96-3587f1daeef1'
                            },
                            'monitoringCssName': {
                                '_value_1': None,
                                'uuid': None
                            },
                            'recordingFlag': 'Automatic Call Recording Enabled',
                            'audibleMwi': 'Default',
                            'speedDial': None,
                            'partitionUsage': 'General',
                            'associatedEndusers': {
                                'enduser': [
                                    {
                                        'userId': enumber
                                    }
                                ]
                            },
                            'missedCallLogging': 'true',
                            'recordingMediaSource': 'Phone Preferred',
                            'ctiid': None,
                            'uuid': xsd.SkipValue
                        },
                        {
                            'index': 2,
                            'label': agent_description,
                            'display': agent_description,
                            'dirn': {
                                'pattern': new_agent_sec_dn,
                                'routePartitionName': {
                                    '_value_1': 'PCCE_DN_PT',
                                    'uuid': '{56339E9D-FD62-199F-552F-0E4DE058FD2A}'
                                },
                                'uuid': secondary_line_uuid
                            },
                            'ringSetting': 'Use System Default',
                            'consecutiveRingSetting': 'Use System Default',
                            'ringSettingIdlePickupAlert': 'Use System Default',
                            'ringSettingActivePickupAlert': 'Use System Default',
                            'displayAscii': agent_description,
                            'e164Mask': end_user_callerID,
                            'dialPlanWizardId': None,
                            'mwlPolicy': 'Use System Policy',
                            'maxNumCalls': 2,
                            'busyTrigger': 1,
                            'callInfoDisplay': {
                                'callerName': 'true',
                                'callerNumber': 'false',
                                'redirectedNumber': 'false',
                                'dialedNumber': 'true'
                            },
                            'recordingProfileName': {
                                '_value_1': 'ZoomCallRec',
                                'uuid': 'e0166dbe-918d-3753-0c96-3587f1daeef1'
                            },
                            'monitoringCssName': {
                                '_value_1': None,
                                'uuid': None
                            },
                            'recordingFlag': 'Automatic Call Recording Enabled',
                            'audibleMwi': 'Default',
                            'speedDial': None,
                            'partitionUsage': 'General',
                            'associatedEndusers': {
                                'enduser': [
                                    {
                                        'userId': enumber
                                    }
                                ]
                            },
                            'missedCallLogging': 'true',
                            'recordingMediaSource': 'Phone Preferred',
                            'ctiid': None,
                            'uuid': xsd.SkipValue
                        }
                    ],
                    'lineIdentifier': None
                }

if single_line == True:
    line = {
                    'line': [
                        {
                            'index': 1,
                            'label': agent_description,
                            'display': agent_description,
                            'dirn': {
                                'pattern': new_agent_pri_dn,
                                'routePartitionName': {
                                    '_value_1': 'PCCE_DN_PT',
                                    'uuid': '{56339E9D-FD62-199F-552F-0E4DE058FD2A}'
                                },
                                'uuid': primary_line_uuid
                            },
                            'ringSetting': 'Use System Default',
                            'consecutiveRingSetting': 'Use System Default',
                            'ringSettingIdlePickupAlert': 'Use System Default',
                            'ringSettingActivePickupAlert': 'Use System Default',
                            'displayAscii': agent_description,
                            'e164Mask': end_user_callerID,
                            'dialPlanWizardId': None,
                            'mwlPolicy': 'Use System Policy',
                            'maxNumCalls': 2,
                            'busyTrigger': 1,
                            'callInfoDisplay': {
                                'callerName': 'true',
                                'callerNumber': 'false',
                                'redirectedNumber': 'false',
                                'dialedNumber': 'true'
                            },
                            'recordingProfileName': {
                                '_value_1': 'ZoomCallRec',
                                'uuid': 'e0166dbe-918d-3753-0c96-3587f1daeef1'
                            },
                            'monitoringCssName': {
                                '_value_1': None,
                                'uuid': None
                            },
                            'recordingFlag': 'Automatic Call Recording Enabled',
                            'audibleMwi': 'Default',
                            'speedDial': None,
                            'partitionUsage': 'General',
                            'associatedEndusers': {
                                'enduser': [
                                    {
                                        'userId': enumber
                                    }
                                ]
                            },
                            'missedCallLogging': 'true',
                            'recordingMediaSource': 'Phone Preferred',
                            'ctiid': None,
                            'uuid': xsd.SkipValue
                        }
                    ],
                    'lineIdentifier': None
                }

#the line was added in and created, this will add in the rest of the important details for the CSF. 
def fill_phone_info(name, owner_user_name):
    phone_info = {
        'name': name,
        'product': 'Cisco Unified Client Services Framework',
        'model': 'Cisco Unified Client Services Framework',
        'description': f'{agent_description}',
        'class': 'Phone',
        'protocol': 'SIP',
        'protocolSide': 'User',
        'devicePoolName': dp,
        'locationName': Location,
        'sipProfileName': 'Standard SIP Profile',
        'mediaResourceListName': MRLN,
        'callingSearchSpaceName': CSS,
        'commonPhoneConfigName': xsd.SkipValue,
        'userLocale': 'English United States',
        'networkLocale': 'United States',
        'phoneTemplateName': xsd.SkipValue,
        'primaryPhoneName': xsd.SkipValue,
        'useTrustedRelayPoint': xsd.SkipValue,
        'builtInBridgeStatus': 'On',
        'packetCaptureMode': xsd.SkipValue,
        'certificateOperation': xsd.SkipValue,
        'deviceMobilityMode': xsd.SkipValue,
        'ownerUserName': owner_user_name,
        'lines': line,
    }
    return phone_info


print("\n")
print("-" * 10)
print("Creating " + device_name)

#create csf with the function above 

associated_devices = device_name
new_phone = fill_phone_info(device_name, owner_user_name)
try:
    resp = service.addPhone(new_phone)
    print('Phone Created')
    print("-" * 10)
    print("\n")
except:
    print('Phone not created, something weird happened.')

print("\n")
print("-" * 10)
print("Updating EndUser")


#update end user with ACG and Line info, and ensure that user is a home user. 
associated_AccessControlGroup = {
                'userGroup': [
                    {
                        'name': 'PCCE Standard User',
                    },
                ]
                }
associated_primary_line = {
                'pattern': new_agent_pri_dn,
                'routePartitionName': 'PCCE_DN_PT'
            }
try:
    resp = service.updateUser(userid=owner_user_name, associatedDevices=associated_devices, primaryExtension=associated_primary_line, associatedGroups=associated_AccessControlGroup, homeCluster=True, imAndPresenceEnable=False)
    print('End User updated')
    print("-" * 10)
    print("\n")
except:
    print('Check end user config, something weird happened.')

print("\n")
print("-" * 10)
print("Updating pguser")
print("-" * 10)
print("\n")

""" here we start updating the app users. sql injection is the best method here 
since updateAppUser would overwrite every other device associated """

sql = '''insert into applicationuserdevicemap (fkapplicationuser, fkdevice, tkuserassociation)
    select au.pkid, d.pkid, 1 from applicationuser au cross join device d 
    where au.name = 'pguser' and d.name in ('{device_name}') and 
    d.pkid not in (select fkdevice from applicationuserdevicemap where fkapplicationuser = au.pkid)'''.format(
        device_name = device_name
    )
try:
    resp = service.executeSQLUpdate( sql )
except Fault as err:
    print('Zeep error: executeSQLUpdate: {err}'.format( err = err ) )
else:
    pguser_update = resp['return']['rowsUpdated']
    if pguser_update == 1:
        print('pguser updated successfully!')
    else:
        print('pguser update failed!')

print("\n")
print("-" * 10)
print("Updating zoomjtapi user")
print("-" * 10)
print("\n")

sql = '''insert into applicationuserdevicemap (fkapplicationuser, fkdevice, tkuserassociation)
    select au.pkid, d.pkid, 1 from applicationuser au cross join device d 
    where au.name = 'zoomjtapi' and d.name in ('{device_name}') and 
    d.pkid not in (select fkdevice from applicationuserdevicemap where fkapplicationuser = au.pkid)'''.format(
        device_name = device_name
    )
try:
    resp = service.executeSQLUpdate( sql )
except Fault as err:
    print('Zeep error: executeSQLUpdate: {err}'.format( err = err ) )
else:
    zoom_update = resp['return']['rowsUpdated']
    if zoom_update == 1:
        print( 'zoomjtapi updated successfully!' )
    else:
        print( 'zoomjtapi update failed!' )