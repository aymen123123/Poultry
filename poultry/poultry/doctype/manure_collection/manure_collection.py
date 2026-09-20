import frappe
from frappe import _
from frappe.model.document import Document

MANURE_ITEM = "MANURE"


class ManureCollection(Document):
	def on_submit(self):
		ensure_manure_item()
		self.make_receipt_stock_entry()
		if self.disposal_type == "بيع":
			self.make_sales_invoice()
		else:
			self.make_disposal_stock_entry()

	def on_cancel(self):
		self.cancel_sales_invoice()
		self.cancel_stock_entry(self.disposal_stock_entry)
		self.cancel_stock_entry(self.receipt_stock_entry)

	def make_receipt_stock_entry(self):
		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"posting_date": self.collection_date,
			"items": [
				{
					"item_code": MANURE_ITEM,
					"qty": self.quantity_kg,
					"t_warehouse": self.warehouse,
					"basic_rate": 0,
				}
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("receipt_stock_entry", stock_entry.name)

	def make_sales_invoice(self):
		if not (self.customer and self.sale_rate):
			frappe.throw(_("Set a Customer and Sale Rate to record the manure sale."))

		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer,
			"posting_date": self.collection_date,
			"update_stock": 1,
			"set_warehouse": self.warehouse,
			"items": [
				{
					"item_code": MANURE_ITEM,
					"qty": self.quantity_kg,
					"rate": self.sale_rate,
					"warehouse": self.warehouse,
				}
			],
		})
		si.insert(ignore_permissions=True)
		si.submit()
		self.db_set("sales_invoice", si.name)

	def make_disposal_stock_entry(self):
		settings = frappe.get_single("Farm Settings")
		if not settings.default_manure_disposal_expense_account:
			frappe.throw(_("Set the Default Manure Disposal Expense Account in Farm Settings first."))

		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"posting_date": self.collection_date,
			"items": [
				{
					"item_code": MANURE_ITEM,
					"qty": self.quantity_kg,
					"s_warehouse": self.warehouse,
					"expense_account": settings.default_manure_disposal_expense_account,
					"cost_center": frappe.db.get_value(
						"Poultry Shed", self.poultry_shed, "linked_cost_center"
					) or settings.default_cost_center,
				}
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("disposal_stock_entry", stock_entry.name)

	def cancel_sales_invoice(self):
		if not self.sales_invoice:
			return
		si = frappe.get_doc("Sales Invoice", self.sales_invoice)
		if si.docstatus == 1:
			si.cancel()

	def cancel_stock_entry(self, stock_entry_name):
		if not stock_entry_name:
			return
		stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()


def ensure_manure_item():
	if frappe.db.exists("Item", MANURE_ITEM):
		return
	item_group = "Products" if frappe.db.exists("Item Group", "Products") else "All Item Groups"
	frappe.get_doc({
		"doctype": "Item",
		"item_code": MANURE_ITEM,
		"item_name": "سماد وفرشة (Manure & Litter)",
		"item_group": item_group,
		"stock_uom": "Kg",
		"is_stock_item": 1,
	}).insert(ignore_permissions=True)
