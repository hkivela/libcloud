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
"""

import xmlrpclib

import libcloud
from libcloud.types import Provider
from libcloud.base import NodeDriver, Node, NodeSize, NodeLocation

API_PREFIX = "http://api.service.softlayer.com/xmlrpc/v3"

DATACENTERS = {
               'sea01': {'country': 'US'},
               'wdc01': {'country': 'US'},
               'dal01': {'country': 'US'}
               }

SOFTLAYER_LOCATION_DAL01 = 3       # Dallas
SOFTLAYER_LOCATION_SEA01 = 18171   # Seattle
SOFTLAYER_LOCATION_WDC01 = 37473   # Washington DC

SOFTLAYER_SERVICE_HARDWARE = 'SoftLayer_Hardware'
SOFTLAYER_SERVICE_VIRTUAL_GUEST = 'SoftLayer_Virtual_Guest'

SOFTLAYER_HOURLY = 'HOURLY'
SOFTLAYER_MONTHLY = 'MONTHLY'

SOFTLAYER_INSTANCE_TYPES = {
    'example': {
        'id': 'example',
        'name': 'Example CCI WDC01 2-core 2GB 100GB 1Gbps',
        'ram': 2048,
        'disk': 100,
        'bandwidth': None,
        'price': None # TODO 
    }
}

SOFTLAYER_TEMPLATES = {
    'example': {
                'complexType': 'SoftLayer_Container_Product_Order_Virtual_Guest',
                'location': SOFTLAYER_LOCATION_WDC01,
                'packageId': 46,
                'prices': [
                           {'id': 1641}, # 2 x 2.0 GHz Cores
                           {'id': 1645}, # 2GB
                           {'id': 905}, # Reboot / Remote Console 
                           {'id': 274}, # 1000 Mbps Public & Private Networks
                           {'id': 1800}, # 0 GB Bandwidth
                           {'id': 21}, # 1 IP Adress
                           {'id': 1639}, # 100 GB (SAN)
                           {'id': 1696}, # Debian GNU/Linux 5.0 Lenny/Stable - Minimal Install (32 bit)
                           {'id': 55}, # Host Ping
                           {'id': 57}, # Email and Ticket
                           {'id': 58}, # Automated Notification
                           {'id': 420}, # Unlimited SSL VPN Users & 1 PPTP VPN User per account
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

    def _get_node_service(self, node):
        if '_service' in node.extra:
            return node.extra['_service']
        return None


    def _to_node(self, host):
        """Convert SoftLayer data to libcloud Node
        
        Note: hardware and virtualGuests data do not have same structure
        
        Note: original host data from SL is stored to extra
        """
        statusId = 0
        if 'statusId' in host:
            statusId = host['statusId']
            host['_service'] = SOFTLAYER_SERVICE_VIRTUAL_GUEST

        if 'hardwareStatusId' in host:
            statusId = host['hardwareStatusId']
            host['_service'] = SOFTLAYER_SERVICE_HARDWARE

        return Node(
            id=host['id'],
            name=host['hostname'],
            state=statusId,
            # IP addresses may be missing just after order
            public_ip=host['primaryIpAddress'] or None,
            private_ip=host['primaryBackendIpAddress'] or None,
            driver=self,
            extra=host
            )

    def _to_nodes(self, hosts):
        return [self._to_node(h) for h in hosts]

    def create_node(self, **kwargs):
        """Order SoftLayer hardware or virtualGuest
        
        See L{NodeDriver.create_node} for more keyword args.

        @keyword    template: Order template name
        @type       template: C{str}
        
        @keyword    virtualGuests: Virtual guest(s) host names and domains
        @type       virtualGuests: C{dict}
        
        """

        if not 'template' in kwargs:
            return None

        template = kwargs["template"]

        if not template in SOFTLAYER_TEMPLATES:
            return None

        order = SOFTLAYER_TEMPLATES[template]

        if 'virtualGuests' in kwargs:
            order['virtualGuests'] = kwargs['virtualGuests']

        result = self.connection.request(
                "SoftLayer_Product_Order",
                "placeOrder",
                order
                )

        # the node is not instantly available trough API, can take a few minutes
        return None
    
    def _to_loc(self, loc):
        return NodeLocation(
            id=loc['id'],
            name=loc['name'],
            country=DATACENTERS[loc['name']]['country'],
            driver=self
        )
 
    def list_locations(self):
        mask = {'SoftLayer_Location': {'regions': {}}}
        
        res = self.connection.request(
            "SoftLayer_Location_Datacenter",
            "getDatacenters",
            object_mask = mask
        )
        
        # checking "in DATACENTERS", because some of the locations returned by 
        # getDatacenters are not useable.
        return [self._to_loc(l) for l in res if l['name'] in DATACENTERS]
 

    def destroy_node(self, node):

        if not '_service' in node.extra:
            return False

        service = node.extra['_service']

        billing_items = []

        if service is SOFTLAYER_SERVICE_HARDWARE:

            # this is usable only for hourly bare metal instances
            # getCurrentBillingDetail throws exception for other types

            if 'bareMetalInstanceFlag'  not in node.extra:
                return False

            if node.extra['bareMetalInstanceFlag'] is not 1:
                return False

            if node.extra['hourlyBillingFlag'] is False:
                return False

            billing_items = self.connection.request(
                                                    service,
                                                    'getCurrentBillingDetail',
                                                    id=node.id
                                                    )

        elif service is SOFTLAYER_SERVICE_VIRTUAL_GUEST:
            billing_items = [self.connection.request(
                                                     service,
                                                     "getBillingItem",
                                                     id=node.id
                                                    )
            ]
        else:
            return False

        if len(billing_items) == 0:
            return False

        for item in billing_items:
            result = self.connection.request(
                "SoftLayer_Billing_Item",
                "cancelService",
                id=item['id']
            )
            if result is False:
                return False

        return True

    def list_nodes(self):
        """Returns all running nodes, including hardware and virtualGuests
        """

        mask = {
                'hardware': {'softwareComponents.passwords': {},
                             'primaryNetworkComponent': {},
                             'primaryBackendNetworkComponent': {},
                             'serverRoom': {},
                             'hourlyBillingFlag': {},
                             },

                'virtualGuests': {
                                  'softwareComponents.passwords': {},
                                  'primaryNetworkComponent': {},
                                  'primaryBackendNetworkComponent': {},
                                  'serverRoom': {},
                                  }
                }

        account = self.connection.request('SoftLayer_Account', 'getObject', object_mask=mask)

        hardware = self._to_nodes(
            account['hardware']
        )

        virtualguests = self._to_nodes(
            account['virtualGuests']
        )

        return hardware + virtualguests

    def list_sizes(self, location=None):
        return [ NodeSize(driver=self.connection.driver, **i)
                    for i in self._instance_types.values() ]

    def reboot_node(self, node, method='hard'):
        """Reboot node
        
        @keyword    method: Method: default, hard or soft
        @type       method: C{str}
        """
        
        if not '_service' in node.extra:
            return False

        REBOOT_METHODS={
                 'default': 'rebootDefault', 
                 'hard': 'rebootHard',
                 'soft': 'rebootSoft'
                 }
        
        if not method in REBOOT_METHODS:
            return False

        service = node.extra['_service']
        
        res = self.connection.request(
            service,
            REBOOT_METHODS[method],
            id=node.id
        )
        return res
