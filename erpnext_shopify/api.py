# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import cint
from .sync_items import sync_items, update_item_stock_qty
from .sync_orders import sync_orders, sync_customers
from .exceptions import ShopifyError

@frappe.whitelist()
def sync_shopify():
	enable_shopify = cint(frappe.db.get_single_value("Shopify Settings", "enable_shopify"))

	if enable_shopify:
		if not frappe.session.user:
			frappe.set_user("Administrator")

		try :
			sync_items()
			sync_customers()
			sync_orders()
			update_item_stock_qty()

		except ShopifyError:
			frappe.db.set_value("Shopify Settings", None, "enable_shopify", 0)

	elif frappe.local.form_dict.cmd == "erpnext_shopify.erpnext_shopify.doctype.shopify_settings.shopify_settings.sync_shopify":
		frappe.throw(_("""Shopify connector is not enabled. Click on 'Connect to Shopify' to connect ERPNext and your Shopify store."""))

