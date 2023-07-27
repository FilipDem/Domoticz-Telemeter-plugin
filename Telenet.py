"""
Python module to get information from Telenet.

Information returned is the internet volume.

Based on https://github.com/KillianMeersman/telemeter
"""

import json
import requests

TELENET = 'https://api.prd.telenet.be'
TELENET_URI_OAUTH = '/ocapi/oauth/userdetails'
TELENET_URI_LOGIN = '/openid/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login'
TELENET_URI_DO_LOGIN = '/openid/login.do'
TELENET_URI_INTERNET_USAGE = '/ocapi/public/api/product-service/v1/products/internet/{}/usage?{}'
TELENET_URI_SUBSCRIPTIONS = '/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=PLAN'
TELENET_URI_CUSTOMERS = '/ocapi/public/api/customer-service/v1/customers'
TELENET_URI_CONTRACT_ADDRESSES = '/ocapi/public/api/contact-service/v1/contact/addresses/{}'
TELENET_URI_BILLING_CYCLE = '/ocapi/public/api/billing-service/v1/account/products/{}/billcycle-details?producttype=internet&count=3'
TELENET_URI_ADDRESS = '/ocapi/public/api/contact-service/v1/contact/addresses/{}'

class Telenet():

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.telemeter_info = None
        self.s = requests.Session()
        self.s.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'

    def login(self):
        # Get OAuth2 state / nonce
        headers = {'x-alt-referer': 'https://www2.telenet.be/nl/klantenservice/#/pages=1/menu=selfservice'}
        try:
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_OAUTH), headers=headers)
        except:
            return False
        
        # Return if already authenticated
        if r.status_code == 200:
            return True

        elif r.status_code == 401:
            state, nonce = r.text.split(',', maxsplit=2)

            # Log in
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_LOGIN.format(state=state, nonce=nonce)))
            data = {'j_username': self.username, 'j_password': self.password, 'rememberme': True}
            try:
                r = self.s.post('{}{}'.format(TELENET, TELENET_URI_DO_LOGIN), data=data)
            except:
                return False
            if r.status_code != 200:
                return False
                
            self.s.headers["X-TOKEN-XSRF"] = self.s.cookies.get("TOKEN-XSRF")
            try:
                r = self.s.get('{}{}'.format(TELENET, TELENET_URI_OAUTH))
            except:
                return False

            if r.status_code == 200:
                return True
        
        return False
        
    def get_user_data(self):
        self.telemeter_info = []
        if self._get_product_subscriptions():
            return True
        else:
            return False

    def telemeter(self):
        current_period = self._get_last_period(self.telemeter_info[0]['businessidentifier'])
        if current_period:
            for i, telemeter in enumerate(self.telemeter_info):
                try:
                    r = self.s.get('{}{}'.format(TELENET, TELENET_URI_INTERNET_USAGE.format(self.telemeter_info[0]['businessidentifier'], current_period)))
                except:
                    return False
                if r.status_code == 200:
                    data = r.json()
                    if data['internet']['totalUsage']['unitType']:
                        self.telemeter_info[i]['total_usage_gb'] = data['internet']['totalUsage']['units']
            return True
        return False
        
    def close(self):
        self.s.close()
        
    def _get_product_subscriptions(self):
        try:
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_SUBSCRIPTIONS))
        except:
            return False
        if r.status_code == 200:
            for subscription in r.json():
                contract = { 'addressId' : subscription['addressId'],
                             'businessidentifier' : subscription['identifier'],
                             'total_usage_gb' : 0 }
                address = self._get_address_from_id(subscription['addressId'])
                if address:
                    contract.update(address)
                self.telemeter_info.append(contract)
            return True
        return False
        
    def _get_address_from_id(self, addressId):
        try:
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_ADDRESS.format(addressId)))
        except:
            return {}
        if r.status_code == 200:
            data = r.json()
            return { 'municipality': data['municipality'],
                     'street': data['street'],
                     'housenr': data['houseNumber'] }
        return {}
        
    def _get_contract_addresses(self):
        try:
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_CUSTOMERS))
        except:
            return False
        if r.status_code == 200:
            data = r.json()
            for address in data['customerLocations']:
                r = self.s.get('{}{}'.format(TELENET, TELENET_URI_CONTRACT_ADDRESSES.format(address['address']['id'])))
                if r.status_code == 200:
                    data = r.json()
                else:
                    return False 
            return True
        return False
            
    def _get_last_period(self, identifier):
        try:
            r = self.s.get('{}{}'.format(TELENET, TELENET_URI_BILLING_CYCLE.format(identifier)))
        except:
            return None
        if r.status_code == 200:
            data = r.json()
            for billperiod in data['billCycles']:
                if billperiod['billCycle'] == 'CURRENT':
                    return 'fromDate={}&toDate={}'.format(billperiod['startDate'], billperiod['endDate'])
        return None

if __name__ == "__main__":

    telenet = Telenet(xxxx, yyyy)
    for i in range(5):
        if telenet.login():
            print('Login successful')
            if telenet.get_user_data():
                print('Contacts found')
                if telenet.telemeter():
                    for product in telenet.telemeter_info:
                        print(product)
            else: 
                print('No user data found.')
        else:
            print('Login failed')
        

