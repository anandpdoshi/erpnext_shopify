# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
import shopify_requests
from .utils import get_shopify_settings
import hashlib, base64, hmac, json
from functools import wraps

def shopify_webhook(f):
	"""
	A decorator thats checks and validates a Shopify Webhook request.
	"""

	def _hmac_is_valid(body, secret, hmac_to_verify):
		secret = str(secret)
		hash = hmac.new(secret, body, hashlib.sha256)
		hmac_calculated = base64.b64encode(hash.digest())
		return hmac_calculated == hmac_to_verify

	@wraps(f)
	def wrapper(*args, **kwargs):
		# Try to get required headers and decode the body of the request.
		try:
			webhook_topic = frappe.local.request.headers.get('X-Shopify-Topic')
			webhook_hmac	= frappe.local.request.headers.get('X-Shopify-Hmac-Sha256')
			webhook_data	= frappe._dict(json.loads(frappe.local.request.get_data()))
		except:
			raise frappe.ValidationError()

		# Verify the HMAC.
		if not _hmac_is_valid(frappe.local.request.get_data(), get_shopify_settings().password, webhook_hmac):
			raise frappe.AuthenticationError()

			# Otherwise, set properties on the request object and return.
		frappe.local.request.webhook_topic = webhook_topic
		frappe.local.request.webhook_data  = webhook_data
		kwargs.pop('cmd')

		return f(*args, **kwargs)
	return wrapper

@frappe.whitelist(allow_guest=True)
@shopify_webhook
def webhook_handler():
	from webhooks import handler_map
	topic = frappe.local.request.webhook_topic
	data = frappe.local.request.webhook_data
	handler = handler_map.get(topic)
	if handler:
		handler(data)

def get_webhooks():
	return shopify_requests.get("/admin/webhooks.json")["webhooks"]

def create_webhooks():
	settings = get_shopify_settings()
	for event in ["orders/create", "orders/delete", "orders/updated", "orders/paid", "orders/cancelled", "orders/fulfilled",
					"orders/partially_fulfilled", "order_transactions/create", "carts/create", "carts/update",
					"checkouts/create", "checkouts/update", "checkouts/delete", "refunds/create", "products/create",
					"products/update", "products/delete", "collections/create", "collections/update", "collections/delete",
					"customer_groups/create", "customer_groups/update", "customer_groups/delete", "customers/create",
					"customers/enable", "customers/disable", "customers/update", "customers/delete", "fulfillments/create",
					"fulfillments/update", "shop/update", "disputes/create", "disputes/update", "app/uninstalled",
					"channels/delete", "product_publications/create", "product_publications/update",
					"product_publications/delete", "collection_publications/create", "collection_publications/update",
					"collection_publications/delete", "variants/in_stock", "variants/out_of_stock"]:

		shopify_requests.post('admin/webhooks.json', json.dumps({
			"webhook": {
				"topic": event,
				"address": settings.webhook_address,
				"format": "json"
			}
		}))

def delete_webhooks():
	for webhook in get_webhooks():
		shopify_requests.delete("/admin/webhooks/{}.json".format(webhook['id']))
