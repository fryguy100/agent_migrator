# agent_migrator

## Overview

The agent_migrator script is designed to take the username of an agent, copy a device profile of a UCCX/PCCE agent, 
migrate the settings over to a CSF profile to enable the agent for Jabber, associates the user to the CSF profile, 
the pguser and the zoom recording application users. Then it cleans up the old CIPC profile of the user and the device profile. 

The cipc_to_csf script is much like the agent_migrator script, but only for agents with CIPC and no Device Profiles.
It also only creates the CSF and associates it to the end user. It does not update the application users. It does
clean up afterwards. 

The scripts are built based on the samples seen in CiscoDevNet/axl-python-zeep-samples repo.

[https://developer.cisco.com/site/axl/](https://developer.cisco.com/site/axl/)

The concepts and techniques shown in that repo can be extended to enable automated management of virtually any configuration or setting in the CUCM admin UI.

## Getting started

* Install Python 3

    On Windows, choose the option to add to PATH environment variable

* If installing on Linux, you may need to install dependencies for `python3-lxml`, see [Installing lxml](https://lxml.de/3.3/installation.html)

  E.g. for Debian/Ubuntu:

  ```bash
  sudo apt build-dep python3-lxml
  ```    

* (Optional) Create/activate a Python virtual environment named `venv`:

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
* Install needed dependency packages:

    ```bash
    pip install -r requirements.txt
    ```

* Edit the `.env` file to specify your CUCM address and AXL user credentials.

* The AXL v11.5 WSDL files are included in this project.  If you'd like to use a different version, replace with the AXL WSDL files for your CUCM version:

    1. From the CUCM Administration UI, download the 'Cisco AXL Tookit' from **Applications** / **Plugins**

    1. Unzip the kit, and navigate to the `schema/current` folder

    1. Copy the three WSDL files to the `schema/` directory of this project: `AXLAPI.wsdl`, `AXLEnums.xsd`, `AXLSoap.xsd`

* To run the specific sample, in Visual Studio Code open the sample `.py` file you want to run, then press `F5`, or open the Debugging panel and click the green 'Launch' arrow

## Hints

* You can get a 'dump' of the AXL WSDL to see how Zeep interprets it by copying the AXL WSDL files to the project root (see above) and running (Mac/Linux):

    ```bash
    python3 -mzeep schema/AXLAPI.wsdl > wsdl.txt
    ```

    This can help with identifying the proper object structure to send to Zeep

* Elements which contain a list, such as:

    ```xml
    <members>
        <member>
            <subElement1/>
            <subElement2/>
        </member>
        <member>
            <subElement1/>
            <subElement2/>
        </member>
    </members>
    ```

    are represented a little differently than expected by Zeep.  Note that `<member>` becomes an array, not `<members>`:

    ```python
    {
        'members': {
            'member': [
                {
                    'subElement1': 'value',
                    'subElement2': 'value'
                },
                {
                    'subElement1': 'value',
                    'subElement2': 'value'
                }
            ]
        }
    }
    ```

* Zeep expects elements with attributes and values to be constructed as below:

    To generate this XML...

    ```xml
    <startChangeId queueId='foo'>bar</startChangeId>
    ```

    Define the object like this...

    ```python
    startChangeId = {
        'queueId': 'foo',
        '_value_1': 'bar'
    }
    ```
* **xsd:SkipValue** When building the XML to send to CUCM, Zeep may include empty elements that are part of the schema but that you didn't explicity specify.  This may result in CUCM interpreting the empty element as indication to set the value to empty/nil/null.  To force Zeep to skip including an element, set its value to `xsd:SkipValue`:

   ```python
   updatePhoneObj = {
    "description": "New Description",
    "lines": xsd:SkipValue
   }
   ```

   Be sure to import the `xsd` module: `from zeep import xsd`

* **Requests Sessions** Creating and using a [requests Session](https://docs.python-requests.org/en/latest/user/advanced/) object [to use with Zeep](https://docs.python-zeep.org/en/master/api.html) allows setting global request parameters like `auth`/`verify`/`headers`.

    In addition, Session retains CUC API `JSESSION` cookies to bypass expensive backend authentication checks per-request, and HTTP persistent connections to keep network latency and networking CPU usage lower.
    
[![published](https://static.production.devnetcloud.com/codeexchange/assets/images/devnet-published.svg)](https://developer.cisco.com/codeexchange/github/repo/CiscoDevNet/axl-python-zeep-sample)
