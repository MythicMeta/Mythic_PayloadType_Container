# Mythic Payload Type Container

The `mythic_payloadtype_container` package creates an easy way to get everything set up in a new PayloadType container for a Mythic supported Payload Type. Mythic is a Command and Control (C2) framework for Red Teaming. The code is on GitHub (https://github.com/its-a-feature/Mythic) and the Mythic project's documentation is on GitBooks (https://docs.mythic-c2.net). This code will be included in the default Mythic Payload Type containers, but is available for anybody making custom containers as well.

## Installation

You can install the mythic scripting interface from PyPI:

```
pip install mythic-payloadtype-container
```

## How to use

This container reports to mythic as version 9 (PyPi version 0.0.45). Use it with Mythic version 2.2.7.
Version 8 (PyPi version 0.0.44 can also be used with Mythic version 2.2.7, it just won't have MythicRPC().execute_c2rpc functionality).

For the main execution of the heartbeat and service functionality, simply import and start the service:
```
from mythic_payloadtype_container import mythic_service
mythic_service.start_service_and_heartbeat(debug=False)
```
You can also pass `debug=True` to the `start_service_and_heartbeat()` function to get detailed debugging information.

You can get the Mythic version of this package with the `get_version_info` function:
```
from mythic_payloadtype_container import get_version_info
get_version_info()
```

## Where is the code?

The code for this PyPi package can be found at https://github.com/MythicMeta/Mythic_PayloadType_Container 
