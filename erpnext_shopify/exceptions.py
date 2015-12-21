from __future__ import unicode_literals
import frappe
from requests.exceptions import HTTPError

class ShopifyError(frappe.ValidationError): pass
