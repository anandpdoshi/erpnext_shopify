# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from erpnext_shopify.exceptions import ShopifyError, HTTPError
from erpnext_shopify import shopify_requests

# from frappe.utils import cstr, flt, nowdate, cint, get_files_path
# from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
# from erpnext_shopify.utils import (get_request, get_shopify_customers, get_address_type, post_request,
# 	get_shopify_items, get_shopify_orders, put_request)

# import base64

class ShopifySettings(Document):
	def validate(self):
		if self.enable_shopify == 1:
			self.validate_access_credentials()
			self.validate_access()

	def validate_access_credentials(self):
		if self.app_type == "Private":
			if not (self.password and self.api_key and self.shopify_url):
				frappe.msgprint(_("Missing value for Passowrd, API Key or Shopify URL"), raise_exception=1)

		else:
			if not (self.access_token and self.shopify_url):
				frappe.msgprint(_("Access token or Shopify URL missing"), raise_exception=1)

	def validate_access(self):
		try:
			shopify_requests.get('/admin/products.json', {"api_key": self.api_key,
				"password": self.password, "shopify_url": self.shopify_url,
				"access_token": self.access_token, "app_type": self.app_type})

		except HTTPError:
			self.set("enable_shopify", 0)
			frappe.throw(_("""Invalid Shopify app credentails or access token"""))


@frappe.whitelist()
def get_series():
	return {
		"sales_order_series" : frappe.get_meta("Sales Order").get_options("naming_series") or "SO-Shopify-",
		"sales_invoice_series" : frappe.get_meta("Sales Invoice").get_options("naming_series")  or "SI-Shopify-",
		"delivery_note_series" : frappe.get_meta("Delivery Note").get_options("naming_series")  or "DN-Shopify-"
	}

