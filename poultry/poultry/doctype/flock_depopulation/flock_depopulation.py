import frappe
from frappe import _
from frappe.model.document import Document

SPENT_HEN_ITEM = "SPENT-HEN"


class FlockDepopulation(Document):
	def on_submit(self):
		self.make_sales_invoice()
		self.scrap_flock_asset()
		self.close_flock()

	def on_cancel(self):
		self.restore_flock_asset()
		self.cancel_sales_invoice()
		self.reopen_flock()

	def get_asset(self):
		return frappe.db.get_value(
			"Flock Capitalization", {"poultry_flock": self.poultry_flock, "docstatus": 1}, "asset"
		)

	def make_sales_invoice(self):
		if not (self.birds_sold_qty and self.sale_amount):
			return
		if not self.customer:
			frappe.throw(_("Set a Customer to record the culled bird sale."))

		ensure_spent_hen_item()

		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer,
			"posting_date": self.depopulation_date,
			"items": [
				{
					"item_code": SPENT_HEN_ITEM,
					"qty": self.birds_sold_qty,
					"rate": self.sale_amount / self.birds_sold_qty,
				}
			],
		})
		si.insert(ignore_permissions=True)
		si.submit()
		self.db_set("sales_invoice", si.name)

	def cancel_sales_invoice(self):
		if not self.sales_invoice:
			return
		si = frappe.get_doc("Sales Invoice", self.sales_invoice)
		if si.docstatus == 1:
			si.cancel()

	def scrap_flock_asset(self):
		asset = self.get_asset()
		if not asset:
			return
		status = frappe.db.get_value("Asset", asset, "status")
		if status in ("Cancelled", "Sold", "Scrapped", "Capitalized"):
			return

		from erpnext.assets.doctype.asset.depreciation import scrap_asset

		scrap_asset(asset, self.depopulation_date)

		je = frappe.db.get_value(
			"GL Entry",
			{"reference_type": "Asset", "reference_name": asset, "voucher_type": "Journal Entry"},
			"voucher_no",
			order_by="creation desc",
		)
		if je:
			self.db_set("disposal_journal_entry", je)

	def restore_flock_asset(self):
		asset = self.get_asset()
		if not asset or frappe.db.get_value("Asset", asset, "status") != "Scrapped":
			return

		from erpnext.assets.doctype.asset.depreciation import restore_asset

		restore_asset(asset)

	def close_flock(self):
		frappe.db.set_value("Poultry Flock", self.poultry_flock, "flock_status", "مغلق")

	def reopen_flock(self):
		frappe.db.set_value("Poultry Flock", self.poultry_flock, "flock_status", "مرسمل")


def ensure_spent_hen_item():
	if frappe.db.exists("Item", SPENT_HEN_ITEM):
		return
	item_group = "Products" if frappe.db.exists("Item Group", "Products") else "All Item Groups"
	frappe.get_doc({
		"doctype": "Item",
		"item_code": SPENT_HEN_ITEM,
		"item_name": "دجاج مستبعد (Spent Hen)",
		"item_group": item_group,
		"stock_uom": "Nos",
		"is_stock_item": 0,
	}).insert(ignore_permissions=True)
