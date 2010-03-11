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
from libcloud.base import NodeDriver, Node

API_PREFIX = "http://api.service.softlayer.com/xmlrpc/v3"

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

    def destroy_node(self, node):
        
        if not 'virtual' in node.extra:
            return False
        
        if node.extra['virtual'] == False:
            return False
        
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
        
        from pprint import pprint
        pprint(account)
        
        hardware = self._to_nodes(
            account['hardware']
        )
        
        virtualguests =  self._to_nodes(
            account['virtualGuests']
        )
        
        return hardware+virtualguests
        

    def reboot_node(self, node):
        res = self.connection.request(
            "SoftLayer_Virtual_Guest", 
            "rebootHard", 
            id=node.id
        )
        return res
