# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import get_request_session
from .exceptions import ShopifyError
import json

def get(path, settings=None):
	if not settings:
		settings = get_shopify_settings()

	s = get_request_session()
	url = get_shopify_url(path, settings)
	r = s.get(url, headers=get_headers(settings))
	r.raise_for_status()
	return r.json()

def post(path, data):
	settings = get_shopify_settings()
	s = get_request_session()
	url = get_shopify_url(path, settings)
	r = s.post(url, data=json.dumps(data), headers=get_headers(settings))
	r.raise_for_status()
	return r.json()

def put(path, data):
	settings = get_shopify_settings()
	s = get_request_session()
	url = get_shopify_url(path, settings)
	r = s.put(url, data=json.dumps(data), headers=get_headers(settings))
	r.raise_for_status()
	return r.json()

def delete(path):
	s = get_request_session()
	url = get_shopify_url(path)
	r = s.delete(url)
	r.raise_for_status()

def get_shopify_items():
	return get('/admin/products.json')['products']

def get_shopify_orders():
	return get('/admin/orders.json')['orders']

def get_shopify_countries():
	return get('/admin/countries.json')['countries']

def get_shopify_customers():
	return get('/admin/customers.json')['customers']

def get_shopify_url(path, settings):
	if settings['app_type'] == "Private":
		return 'https://{}:{}@{}/{}'.format(settings['api_key'], settings['password'], settings['shopify_url'], path)
	else:
		return 'https://{}/{}'.format(settings['shopify_url'], path)

def get_headers(settings):
	headers = {'Content-Type': 'application/json'}

	if settings['app_type'] == "Private":
		return headers
	else:
		headers["X-Shopify-Access-Token"] = settings['access_token']
		return headers

def get_shopify_settings():
	d = frappe.get_doc("Shopify Settings")
	if d.shopify_url:
		return d.as_dict()
	else:
		frappe.throw(_("Shopify store URL is not configured on Shopify Settings"), ShopifyError)
