# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# libcloud.org licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Softlayer driver

THIS IS WORK IN PROGRESS, NOT READY FOR ANYTHING BUT REVIEW AND COMMENTS.

PLEASE GO TROUGH SOFTLAYER DOCUMENTATION BEFORE DOING ANYTHING STUPID.

IT'S POSSIBLE TO MAKE RATHER EXPENSIVE ORDERS TROUGH THIS API SO BE ABSOLUTELY
SURE YOU KNOW WHAT YOU'RE DOING.

...

Get familiar with SoftLayer API:

http://sldn.softlayer.com/wiki/index.php/The_SoftLayer_API

Thread about XML-RPC complexType support:

http://forums.softlayer.com/showthread.php?t=4756

XML-RPC ordering Python example from klaude:

http://gist.github.com/328806

...

It's possible to construct a wide variety of orders

You can get sample templates by manually ordering and then:

virtual_guest_id = 12345 # get this from node.id

template = driver.connection.request(
                "SoftLayer_Virtual_Guest",
                "getOrderTemplate",
                'HOURLY',
                id=virtual_guest_id)
                
from pprint import pprint
pprint(template)

This will return a lot of data but you can extract the price IDs from there


There's one example in SOFTLAYER_INSTANCE_TYPES, SOFTLAYER_TEMPLATES

To order that example, you would:

SoftLayer = get_driver(Provider.SOFTLAYER) 
driver = SoftLayer('SL12345', 'YOUR-VERY-SECRET_KEY') # change these
        
result = driver.create_node(template='example', 
                            virtualGuests=[{'hostname': 'testhost', 
                                        'domain': 'testdomain.com'}])

"""

import xmlrpclib

import libcloud
from libcloud.types import Provider
from libcloud.base import NodeDriver, Node, NodeSize

API_PREFIX = "http://api.service.softlayer.com/xmlrpc/v3"

# TODO: should use the codes WDC01 etc instead
SOFTLAYER_LOCATION_DALLAS = 3 
SOFTLAYER_LOCATION_SEATTLE = 18171
SOFTLAYER_LOCATION_WASHINGTON_DC = 37473


SOFTLAYER_HOURLY = 'HOURLY'
SOFTLAYER_MONTHLY = 'MONTHLY'

SOFTLAYER_INSTANCE_TYPES = {
    'example': {
        'id': 'example',
        'name': 'Example CCI WDC01 2-core 2GB 100GB 1Gbps',
        'ram': 2048,
        'disk': 100,
        'bandwidth': None,
        'price': None # TODO... 
    }
}

SOFTLAYER_TEMPLATES = {
    'example': {
                'complexType': 'SoftLayer_Container_Product_Order_Virtual_Guest',
                'location': SOFTLAYER_LOCATION_WASHINGTON_DC,
                'packageId': 46,
                'prices': [
                           {'id': 1641}, # 2 x 2.0 GHz Cores
                           {'id': 1645}, # 2GB
                           {'id': 905},  # Reboot / Remote Console 
                           {'id': 274},  # 1000 Mbps Public & Private Networks
                           {'id': 1800}, # 0 GB Bandwidth
                           {'id': 21},   # 1 IP Adress
                           {'id': 1639}, # 100 GB (SAN)
                           {'id': 1696}, # Debian GNU/Linux 5.0 Lenny/Stable - Minimal Install (32 bit)
                           {'id': 55},   # Host Ping
                           {'id': 57},   # Email and Ticket
                           {'id': 58},   # Automated Notification
                           {'id': 420},  # Unlimited SSL VPN Users & 1 PPTP VPN User per account
                           {'id': 418}   # Nessus Vulnerability Assessment & Reporting
                           ],
                'quantity': 1,
                'useHourlyPricing': True,
                'virtualGuests': \
                    [{'domain': 'example.org', 'hostname': 'newcci'}]
                }
}  

class SoftLayerException(Exception):
    pass

class SoftLayerTransport(xmlrpclib.Transport):
    user_agent = "libcloud/%s (SoftLayer)" % libcloud.__version__

class SoftLayerProxy(xmlrpclib.ServerProxy):
    transportCls = SoftLayerTransport

    def __init__(self, service, verbose=0):
        xmlrpclib.ServerProxy.__init__(
            self,
            uri="%s/%s" % (API_PREFIX, service),
            transport=self.transportCls(use_datetime=0),
            verbose=verbose
        )

class SoftLayerConnection(object):
    proxyCls = SoftLayerProxy
    driver = None

    def __init__(self, user, key):
        self.user = user
        self.key = key 

    def request(self, service, method, *args, **init_params):
        """Do XML-RPC request against SoftLayer API
        
        init_params can have optional 'id' or 'object_mask' to identify
        object to get and/or set the object_mask                
        """
        sl = self.proxyCls(service)
                
        params = [self._get_headers(service, init_params)] + list(args)
        try:
            return getattr(sl, method)(*params)
        except xmlrpclib.Fault, e:
            raise SoftLayerException(e)

    def _get_headers(self, service, init_params=None):
        
        if not init_params:
            init_params = {}

        headers = {                   
                   'authenticate': {
                            'username': self.user,
                            'apiKey': self.key
                            }                                        
        }
        
        if 'id' in init_params:
            headers['%sInitParameters' % service] = {'id': init_params['id']}

        if 'object_mask' in init_params:                        
            headers['%sObjectMask' % service] = \
                {'mask': init_params['object_mask']}

        return { 'headers': headers }            
        

class SoftLayerNodeDriver(NodeDriver):
    connectionCls = SoftLayerConnection
    name = 'SoftLayer'
    type = Provider.SOFTLAYER
    
    
    _instance_types = SOFTLAYER_INSTANCE_TYPES

    def __init__(self, key, secret=None, secure=False):
        self.key = key
        self.secret = secret
        self.connection = self.connectionCls(key, secret)
        self.connection.driver = self

    def _to_node(self, host):
        """Convert SoftLayer data to libcloud Node
        
        Note: hardware and virtualGuests data doesn't have same structure
        
        Note: original host data from SL is stored to extra
        """
        statusId = 0
        if 'statusId' in host:
            statusId = host['statusId']
            
        if 'hardwareStatusId' in host:
            statusId = host['hardwareStatusId']            
        
        return Node(
            id=host['id'],
            name=host['hostname'],
            state=statusId,
            public_ip=host['primaryIpAddress'],
            private_ip=host['primaryBackendIpAddress'],
            driver=self,
            extra=host
            )
    
    def _to_nodes(self, hosts):
        return [self._to_node(h) for h in hosts]

    def create_node(self, **kwargs):
        """Order SoftLayer hardware or virtualGuest
        
        NOTE: WORK IN PROGRESS
        
        See that request at end and it's comment
        
        TODO: Ordering hardware

        # TODO: virtualGuests documentation
        
        # TODO: quantity
        
        # TODO: hourly,monthly pricing (this is maybe better left in templates)

        See L{NodeDriver.create_node} for more keyword args.

        @keyword    template: Order template name
        @type       template: C{str}
        
        
        """
        
        if not 'template' in kwargs:
            # TODO, throw exception or ?
            return None
                
        template = kwargs["template"]
    
        if not template in SOFTLAYER_TEMPLATES:
            # TODO ...
            return None
    
        order = SOFTLAYER_TEMPLATES[template]
    
        if 'virtualGuests' in kwargs:
            order['virtualGuests'] = kwargs['virtualGuests']
            
    
        result = self.connection.request(
                "SoftLayer_Product_Order",
                "verifyOrder", # change this to placeOrder and it works :)
                order
                )
    
        # the node is not instantly available, can take a few minutes
        return None
    
    
    def destroy_node(self, node):
        
        # TODO: check if hardware or virtualGuest!
        
        billing_item = self.connection.request(
            "SoftLayer_Virtual_Guest",
            "getBillingItem",
            id=node.id
        )

        if billing_item:
            res = self.connection.request(
                "SoftLayer_Billing_Item",
                "cancelService",
                id=billing_item['id']
            )
            return res
        else:
            return False

    

    def list_nodes(self):
        """Returns all running nodes, including hardware and virtualGuests
        """
                
        mask = {                
                'hardware': {'softwareComponents.passwords': {}, 
                             'primaryNetworkComponent': {},
                             'primaryBackendNetworkComponent': {}, 
                             'serverRoom': {},
                             },
                             
                'virtualGuests': {
                                  'softwareComponents.passwords': {}, 
                                  'primaryNetworkComponent': {}, 
                                  'primaryBackendNetworkComponent': {}, 
                                  'serverRoom': {},
                                  }                       
                }
        
        account = self.connection.request('SoftLayer_Account', 'getObject', object_mask = mask)
        
        hardware = self._to_nodes(
            account['hardware']
        )
        
        virtualguests =  self._to_nodes(
            account['virtualGuests']
        )
        
        return hardware+virtualguests
     
    def list_sizes(self, location=None):
        return [ NodeSize(driver=self.connection.driver, **i) 
                    for i in self._instance_types.values() ]   

    def reboot_node(self, node):
        # TODO: hardware support again
        res = self.connection.request(
            "SoftLayer_Virtual_Guest", 
            "rebootHard", 
            id=node.id
        )
        return res
