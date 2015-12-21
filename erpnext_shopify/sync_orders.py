# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _

def sync_customers():
	sync_shopify_customers()
	sync_erp_customers()

def sync_shopify_customers():
	for customer in get_shopify_customers():
		if not frappe.db.get_value("Customer", {"shopify_id": customer.get('id')}, "name"):
			create_customer(customer)

def create_customer(customer):
	erp_cust = None
	cust_name = (customer.get("first_name") + " " + (customer.get("last_name") and  customer.get("last_name") or ""))\
		if customer.get("first_name") else customer.get("email")

	try:
		erp_cust = frappe.get_doc({
			"doctype": "Customer",
			"name": customer.get("id"),
			"customer_name" : cust_name,
			"shopify_id": customer.get("id"),
			"customer_group": "Commercial",
			"territory": "All Territories",
			"customer_type": "Company"
		}).insert()
	except:
		pass

	if erp_cust:
		create_customer_address(erp_cust, customer)

def create_customer_address(erp_cust, customer):
	for i, address in enumerate(customer.get("addresses")):
		frappe.get_doc({
			"doctype": "Address",
			"address_title": erp_cust.customer_name,
			"address_type": get_address_type(i),
			"address_line1": address.get("address1") or "Address 1",
			"address_line2": address.get("address2"),
			"city": address.get("city") or "City",
			"state": address.get("province"),
			"pincode": address.get("zip"),
			"country": address.get("country"),
			"phone": address.get("phone"),
			"email_id": customer.get("email"),
			"customer": erp_cust.name,
			"customer_name":  erp_cust.customer_name
		}).insert()

def sync_erp_customers():
	for customer in frappe.db.sql("""select name, customer_name from tabCustomer where ifnull(shopify_id, '') = ''
		and sync_with_shopify = 1 """, as_dict=1):
		cust = {
			"first_name": customer['customer_name']
		}

		addresses = frappe.db.sql("""select addr.address_line1 as address1, addr.address_line2 as address2,
						addr.city as city, addr.state as province, addr.country as country, addr.pincode as zip from
						tabAddress addr where addr.customer ='%s' """%(customer['customer_name']), as_dict=1)

		if addresses:
			cust["addresses"] = addresses

		cust = post_request("/admin/customers.json", { "customer": cust})

		customer = frappe.get_doc("Customer", customer['name'])
		customer.shopify_id = cust['customer'].get("id")
		customer.save()

def sync_orders():
	sync_shopify_orders()

def sync_shopify_orders():
	for order in get_shopify_orders():
		validate_customer_and_product(order)
		create_order(order)

def validate_customer_and_product(order):
	if not frappe.db.get_value("Customer", {"shopify_id": order.get("customer").get("id")}, "name"):
		create_customer(order.get("customer"))

	warehouse = frappe.get_doc("Shopify Settings", "Shopify Settings").warehouse
	for item in order.get("line_items"):
		if not frappe.db.get_value("Item", {"shopify_id": item.get("product_id")}, "name"):
			item = get_request("/admin/products/{}.json".format(item.get("product_id")))["product"]
			make_item(warehouse, item)

def create_order(order):
	shopify_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	so = create_salse_order(order, shopify_settings)
	if order.get("financial_status") == "paid":
		create_sales_invoice(order, shopify_settings, so)

	if order.get("fulfillments"):
		create_delivery_note(order, shopify_settings, so)

def create_salse_order(order, shopify_settings):
	so = frappe.db.get_value("Sales Order", {"shopify_id": order.get("id")}, "name")
	if not so:
		so = frappe.get_doc({
			"doctype": "Sales Order",
			"naming_series": shopify_settings.sales_order_series or "SO-Shopify-",
			"shopify_id": order.get("id"),
			"customer": frappe.db.get_value("Customer", {"shopify_id": order.get("customer").get("id")}, "name"),
			"delivery_date": nowdate(),
			"selling_price_list": shopify_settings.price_list,
			"ignore_pricing_rule": 1,
			"apply_discount_on": "Net Total",
			"discount_amount": get_discounted_amount(order),
			"items": get_item_line(order.get("line_items"), shopify_settings),
			"taxes": get_tax_line(order, order.get("shipping_lines"), shopify_settings)
		}).insert()

		so.submit()

	else:
		so = frappe.get_doc("Sales Order", so)

	return so

def create_sales_invoice(order, shopify_settings, so):
	if not frappe.db.get_value("Sales Invoice", {"shopify_id": order.get("id")}, "name") and so.docstatus==1 \
		and not so.per_billed:
		si = make_sales_invoice(so.name)
		si.shopify_id = order.get("id")
		si.naming_series = shopify_settings.sales_invoice_series or "SI-Shopify-"
		si.is_pos = 1
		si.cash_bank_account = shopify_settings.cash_bank_account
		si.submit()

def create_delivery_note(order, shopify_settings, so):
	for fulfillment in order.get("fulfillments"):
		if not frappe.db.get_value("Delivery Note", {"shopify_id": fulfillment.get("id")}, "name") and so.docstatus==1:
			dn = make_delivery_note(so.name)
			dn.shopify_id = fulfillment.get("id")
			dn.naming_series = shopify_settings.delivery_note_series or "DN-Shopify-"
			dn.items = update_items_qty(dn.items, fulfillment.get("line_items"), shopify_settings)
			dn.save()

def update_items_qty(dn_items, fulfillment_items, shopify_settings):
	return [dn_item.update({"qty": item.get("quantity")}) for item in fulfillment_items for dn_item in dn_items\
		 if get_item_code(item) == dn_item.item_code]

def get_discounted_amount(order):
	discounted_amount = 0.0
	for discount in order.get("discount_codes"):
		discounted_amount += flt(discount.get("amount"))
	return discounted_amount

def get_item_line(order_items, shopify_settings):
	items = []
	for item in order_items:
		item_code = get_item_code(item)
		items.append({
			"item_code": item_code,
			"item_name": item.get("name"),
			"rate": item.get("price"),
			"qty": item.get("quantity"),
			"stock_uom": item.get("sku"),
			"warehouse": shopify_settings.warehouse
		})
	return items

def get_tax_line(order, shipping_lines, shopify_settings):
	taxes = []
	for tax in order.get("tax_lines"):
		taxes.append({
			"charge_type": _("On Net Total"),
			"account_head": get_tax_account_head(tax),
			"description": tax.get("title") + "-" + cstr(tax.get("rate") * 100.00),
			"rate": tax.get("rate") * 100.00,
			"included_in_print_rate": set_included_in_print_rate(order)
		})

	taxes = update_taxes_with_shipping_rule(taxes, shipping_lines)

	return taxes

def set_included_in_print_rate(order):
	if order.get("total_tax"):
		if (flt(order.get("total_price")) - flt(order.get("total_line_items_price"))) == 0.0:
			return 1
	return 0

def update_taxes_with_shipping_rule(taxes, shipping_lines):
	for shipping_charge in shipping_lines:
		taxes.append({
			"charge_type": _("Actual"),
			"account_head": get_tax_account_head(shipping_charge),
			"description": shipping_charge["title"],
			"tax_amount": shipping_charge["price"]
		})

	return taxes

def get_tax_account_head(tax):
	tax_account =  frappe.db.get_value("Shopify Tax Account", \
		{"parent": "Shopify Settings", "shopify_tax": tax.get("title")}, "tax_account")

	if not tax_account:
		frappe.throw("Tax Account not specified for Shopify Tax {}".format(tax.get("title")))

	return tax_account
