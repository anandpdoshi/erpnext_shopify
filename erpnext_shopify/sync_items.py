# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
import shopify_requests

"""
Note:
	1. `shopify_item`: Item dict derived from Shopify via a request
	1. `item`: ERPNext Item doc
	1. When an item exists in both ERPNext and Shopify, Shopify becomes the source of Item description, image, etc.
"""

def sync_items():
	"""Sync items between Shopify and ERPNext"""
	shopify_settings = shopify_requests.get_shopify_settings()
	shopify_items = shopify_requests.get_shopify_items()

	for shopify_item in shopify_items:
		sync_item_from_shopify(shopify_item, shopify_settings)

	shopify_item_map = dict((shopify_item["id"], shopify_item) for shopify_item in shopify_items)
	for item in frappe.get_all("Item", filters={"sync_with_shopify": 1, "variant_of": ""}):
		sync_item_to_shopify(item, shopify_settings, shopify_item_map)

# From Shopify -------------------------------------------
def sync_item_from_shopify(shopify_item, shopify_settings):
	shopify_item = frappe._dict(shopify_item)
	shopify_item.product_id = shopify_item.id

	if is_template_item(shopify_item):
		# this is a template item with all its variants
		shopify_item.has_variants = 1
		shopify_item.attributes = sync_item_attributes(shopify_item.options)
		sync_item(shopify_item, shopify_settings)
		sync_variants(shopify_item, shopify_settings)

	else:
		# else it is an item without variants
		shopify_item.variant_id = shopify_item.variants[0]["id"]
		sync_item(shopify_item, shopify_settings)

def is_template_item(shopify_item):
	if len(shopify_item.get("options")) >= 1 and "Default Title" not in shopify_item.get("options")[0]["values"]:
		return True
	else:
		return False

def sync_item_attributes(attributes):
	"""Create Item Attribute records if missing and sync attribute values.
	Note: Item Attribute is a setup doctype and is different from Item Variant Attribute which is a child of Item"""
	attributes = []
	for attr in attributes:
		if not frappe.db.get_value("Item Attribute", attr.get("name"), "name"):
			# Item Attribute is missing
			frappe.get_doc({
				"doctype": "Item Attribute",
				"attribute_name": attr.get("name"),
				"item_attribute_values": [{"attribute_value":attr_value, "abbr": cstr(attr_value)[:3]} for attr_value in attr.get("values")]
			}).insert()

		else:
			# sync attribute values only
			item_attr = frappe.get_doc("Item Attribute", attr.get("name"))
			for attr_value in attr.get("values"):
				if not any((d.abbr == attr_value or d.attribute_value == attr_value) for d in item_attr.item_attribute_values):
					item_attr.append("item_attribute_values", {
						"attribute_value": attr_value,
						"abbr": cstr(attr_value)[:3]
					})
			item_attr.save()

		attributes.append({"attribute": attr.get("name")})

	return attributes

def sync_item(shopify_item, shopify_settings):
	shopify_product_id = shopify_item.product_id
	shopify_variant_id = shopify_item.variant_id

	item = get_item(shopify_product_id, shopify_variant_id)
	if not item:
		item = frappe.new_doc("Item")
		item.item_code = shopify_item.variant_id or shopify_item.product_id

		# UOM is hardcoded here because Shopify does not have UOMs
		item.stock_uom = _("Nos")

	item_group = sync_item_group(shopify_item.product_type)

	item.update({
		# TODO ensure these are mandatory
		"sync_with_shopify": 1,
		"shopify_id": shopify_item.product_id,
		"shopify_variant_id": shopify_variant_id.variant_id,

		"has_variants": shopify_item.has_variants,
		"variant_of": shopify_item.variant_of,

		"item_name": shopify_item.title,
		"description": shopify_item.body_html or shopify_item.title,
		"item_group": item_group,

		# doing list() to make a copy
		"attributes": list(shopify_item.attributes or []),

		"stock_keeping_unit": shopify_item.sku or shopify_item.variants[0].get("sku"),
		"default_warehouse": shopify_settings.warehouse,
		"image": (shopify_item.image or {}).get("src") or item.image
	})

	item.save()

	if not shopify_item.has_variants:
		sync_price_list(shopify_item, shopify_settings, item)

def get_item(shopify_product_id, shopify_variant_id=None):
	filters = {"shopify_id": shopify_product_id}
	if shopify_variant_id:
		filters["shopify_variant_id"] = shopify_variant_id

	try:
		return frappe.get_doc("Item", filters)
	except frappe.DoesNotExistError:
		frappe.message_log and frappe.message_log.pop()
		return None

def sync_item_group(product_type):
	if product_type and not frappe.db.get_value("Item Group", product_type):
		frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": product_type,
			"parent_item_group": _("All Item Groups"),
			"is_group": "No"
		}).insert()

	return product_type or _("All Item Groups")

def sync_price_list(shopify_item, shopify_settings, item):
	filters = {"item_code": item.name, "price_list": shopify_settings.price_list}

	try:
		item_price = frappe.get_doc("Item Price", filters)
	except frappe.DoesNotExistError:
		frappe.message_log and frappe.message_log.pop()

		item_price = frappe.new_doc("Item Price")
		item_price.update(filters)

	item_price.price_list_rate = shopify_item.price or shopify_item.variants[0].get("price")
	item_price.save()

def sync_variants(shopify_item, shopify_settings):
	template_item = frappe.db.get_value("Item",
		filters={"shopify_id": shopify_item.product_id, "has_variants": 1},
		fieldname=["name", "stock_uom"],
		as_dict=True)

	for variant in shopify_item.variants:
		# prepare shopify variant item for sync_item() call
		variant = frappe._dict(variant)

		variant_attributes = list(shopify_item.attributes)

		# parepare shopify variant item
		shopify_variant_item = frappe._dict({
			"product_id": variant.product_id,
			"variant_id": variant.id,
			"title": shopify_item.title,
			"product_type": shopify_item.product_type,
			"sku": variant.sku,
			"uom": template_item.uom or _("Nos"),
			"price": variant.price,
			"attributes": variant_attribute
		})

		# prepare attributes
		# shopify only allows 3 attributes for a variant
		for i, attr in enumerate(("option1", "option2", "option3")):
			attr_value = variant.get(attr)
			if attr_value:
				variant_attribute = variant_attribute[i]
				variant_attribute.update({
					"attribute_value": _get_attribute_value(variant_attribute["attribute"], attr_value)
				})

		sync_item(shopify_variant_item, shopify_settings)

def _get_attribute_value(attribute, possible_attribute_value):
	"""Shopify could pass the exact attribute value or its abbreviation"""
	attribute_value = frappe.db.sql("""select attribute_value from `tabItem Attribute Value`
		where parent=%s and (abbr = %s or attribute_value = %s)""", (attribute, possible_attribute_value, possible_attribute_value))

	return attribute_value[0][0] if attribute_value else None


# To Shopify -------------------------------------------
def sync_item_to_shopify(item, shopify_settings, shopify_item_map):
	shopify_item = {
		"product": {
			"title": item.item_name,
			"body_html": item.description,
			"product_type": item.item_group,

			# main item or its variants
			# there is always 1 variant
			"variants": [],

			# list of attributes
			"options": []
		}
	}

	if item.has_variants:
		variants = []
		for i, variant in enumerate(frappe.get_all("Item", filters={"variant_of": item.name, "sync_with_shopify": 1})):
			variant_item = frappe.get_doc("Item", variant)
			variants.append(get_price_and_stock(item, shopify_settings))

	else:
		variants = [get_price_and_stock(item, shopify_settings)]



def sync_item_with_shopify(item, price_list, warehouse):
	variant_item_code_list = []

	item_data = { "product":
		{ "title": item.get("item_name"),
		"body_html": item.get("description"),
		"product_type": item.get("item_group")}
	}

	if item.get("has_variants"):
		variant_list, options, variant_item_code = get_variant_attributes(item, price_list, warehouse)

		item_data["product"]["variants"] = variant_list
		item_data["product"]["options"] = options

		variant_item_code_list.extend(variant_item_code)

	else:
		item_data["product"]["variants"] = [get_price_and_stock_details(item, warehouse, price_list)]

	erp_item = frappe.get_doc("Item", item.get("item_code"))

	# check if the item really exists on shopify
	if item.get("shopify_id"):
		try:
			get_request("/admin/products/{}.json".format(item.get("shopify_id")))
		except requests.exceptions.HTTPError, e:
			if e.args[0] and e.args[0].startswith("404"):
				item["shopify_id"] = None

			else:
				raise

	if not item.get("shopify_id"):
		new_item = post_request("/admin/products.json", item_data)
		erp_item.shopify_id = new_item['product'].get("id")

		if not item.get("has_variants"):
			erp_item.shopify_variant_id = new_item['product']["variants"][0].get("id")

		erp_item.save()

		update_variant_item(new_item, variant_item_code_list)

	else:
		item_data["product"]["id"] = item.get("shopify_id")
		put_request("/admin/products/{}.json".format(item.get("shopify_id")), item_data)

	sync_item_image(erp_item)

def sync_item_image(item):
	image_info = {
        "image": {}
	}

	if item.image:
		img_details = frappe.db.get_value("File", {"file_url": item.image}, ["file_name", "content_hash"])

		if img_details and img_details[0] and img_details[1]:
			is_private = item.image.startswith("/private/files/")
			with open(get_files_path(img_details[0].strip("/"), is_private=is_private), "rb") as image_file:
			    image_info["image"]["attachment"] = base64.b64encode(image_file.read())
			image_info["image"]["filename"] = img_details[0]

		elif item.image.startswith("http") or item.image.startswith("ftp"):
			image_info["image"]["src"] = item.image

		if image_info["image"]:
			post_request("/admin/products/{0}/images.json".format(item.shopify_id), image_info)

def update_variant_item(new_item, item_code_list):
	for i, item_code in enumerate(item_code_list):
		erp_item = frappe.get_doc("Item", item_code)
		erp_item.shopify_id = new_item['product']["variants"][i].get("id")
		erp_item.shopify_variant_id = new_item['product']["variants"][i].get("id")
		erp_item.save()

def get_variant_attributes(item, price_list, warehouse):
	options, variant_list, variant_item_code = [], [], []
	attr_dict = {}

	for i, variant in enumerate(frappe.get_all("Item", filters={"variant_of": item.get("item_code")},
		fields=['name'])):

		item_variant = frappe.get_doc("Item", variant.get("name"))
		variant_list.append(get_price_and_stock_details(item_variant, warehouse, price_list))

		for attr in item_variant.get('attributes'):
			if not attr_dict.get(attr.attribute):
				attr_dict.setdefault(attr.attribute, [])

			attr_dict[attr.attribute].append(attr.attribute_value)

			if attr.idx <= 3:
				variant_list[i]["option"+cstr(attr.idx)] = attr.attribute_value

		variant_item_code.append(item_variant.item_code)

	for i, attr in enumerate(attr_dict):
		options.append({
            "name": attr,
            "position": i+1,
            "values": list(set(attr_dict[attr]))
        })

	return variant_list, options, variant_item_code

def get_price_and_stock_details(item, warehouse, price_list):
	qty = frappe.db.get_value("Bin", {"item_code":item.get("item_code"), "warehouse": warehouse}, "actual_qty")
	price = frappe.db.get_value("Item Price", \
			{"price_list": price_list, "item_code":item.get("item_code")}, "price_list_rate")

	item_price_and_quantity = {
		"price": flt(price),
		"inventory_quantity": cint(qty) if qty else 0,
		"inventory_management": "shopify"
	}
	if item.shopify_variant_id:
		item_price_and_quantity["id"] = item.shopify_variant_id

	return item_price_and_quantity

def get_item_code(item):
	item_code = frappe.db.get_value("Item", {"shopify_id": item.get("variant_id")}, "item_code")
	if not item_code:
		item_code = frappe.db.get_value("Item", {"shopify_id": item.get("product_id")}, "item_code")

	return item_code

def trigger_update_item_stock(doc, method):
	shopify_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	if shopify_settings.shopify_url and shopify_settings.enable_shopify:
		update_item_stock(doc.item_code, shopify_settings, doc)

def update_item_stock_qty():
	shopify_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	for item in frappe.get_all("Item", fields=['name', "item_code"], filters={"sync_with_shopify": 1}):
		update_item_stock(item.item_code, shopify_settings)

def update_item_stock(item_code, shopify_settings, doc=None):
	item = frappe.get_doc("Item", item_code)

	if not doc:
		bin_name = frappe.db.get_value("Bin", {"warehouse": shopify_settings.warehouse,
			"item_code": item_code}, "name")

		if bin_name:
			doc = frappe.get_doc("Bin", bin_name)

	if doc:
		if not item.shopify_id and not item.variant_of:
			sync_item_with_shopify(item, shopify_settings.price_list, shopify_settings.warehouse)

		if item.sync_with_shopify and item.shopify_id and shopify_settings.warehouse == doc.warehouse:
			if item.variant_of:
				item_data, resource = get_product_update_dict_and_resource(frappe.get_value("Item",
					item.variant_of, "shopify_id"), item.shopify_variant_id)

			else:
				item_data, resource = get_product_update_dict_and_resource(item.shopify_id, item.shopify_variant_id)

			item_data["product"]["variants"][0].update({
				"inventory_quantity": cint(doc.actual_qty),
				"inventory_management": "shopify"
			})

			put_request(resource, item_data)

def get_product_update_dict_and_resource(shopify_id, shopify_variant_id):
	"""
	JSON required to update product

	item_data =	{
		    "product": {
		        "id": 3649706435 (shopify_id),
		        "variants": [
		            {
		                "id": 10577917379 (shopify_variant_id),
		                "inventory_management": "shopify",
		                "inventory_quantity": 10
		            }
		        ]
		    }
		}
	"""

	item_data = {
		"product": {
			"variants": []
		}
	}

	item_data["product"]["id"] = shopify_id
	item_data["product"]["variants"].append({
		"id": shopify_variant_id
	})

	resource = "admin/products/{}.json".format(shopify_id)

	return item_data, resource
