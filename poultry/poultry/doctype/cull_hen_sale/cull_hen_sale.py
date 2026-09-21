import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from poultry.poultry.doctype.flock_depopulation.flock_depopulation import (
	SPENT_HEN_ITEM,
	ensure_spent_hen_item,
)


class CullHenSale(Document):
	def validate(self):
		self.current_flock_qty = frappe.db.get_value("Poultry Flock", self.poultry_flock, "current_qty") or 0
		if self.birds_sold_qty > self.current_flock_qty:
			frappe.throw(
				_("Birds sold ({0}) cannot exceed the current flock qty ({1}).").format(
					self.birds_sold_qty, self.current_flock_qty
				)
			)
		self.set_asset_value_reduction()

	def get_asset(self):
		return frappe.db.get_value(
			"Flock Capitalization", {"poultry_flock": self.poultry_flock, "docstatus": 1}, "asset"
		)

	def set_asset_value_reduction(self):
		self.asset = self.get_asset()
		if not self.asset:
			self.current_asset_value = 0
			self.new_asset_value = 0
			return

		status = frappe.db.get_value("Asset", self.asset, "status")
		if status in ("Cancelled", "Sold", "Scrapped"):
			self.asset = None
			self.current_asset_value = 0
			self.new_asset_value = 0
			return

		self.current_asset_value = flt(
			frappe.db.get_value("Asset", self.asset, "value_after_depreciation")
		)
		if self.current_flock_qty:
			remaining_share = flt(self.current_flock_qty - self.birds_sold_qty) / self.current_flock_qty
		else:
			remaining_share = 0
		self.new_asset_value = self.current_asset_value * remaining_share

	def on_submit(self):
		self.reduce_flock_count()
		self.make_sales_invoice()
		self.make_asset_value_adjustment()

	def on_cancel(self):
		self.cancel_asset_value_adjustment()
		self.cancel_sales_invoice()
		self.restore_flock_count()

	def reduce_flock_count(self):
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		flock.db_set("current_qty", (flock.current_qty or 0) - self.birds_sold_qty)

	def restore_flock_count(self):
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		flock.db_set("current_qty", (flock.current_qty or 0) + self.birds_sold_qty)

	def make_sales_invoice(self):
		ensure_spent_hen_item()
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": self.customer,
			"posting_date": self.sale_date,
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

	def make_asset_value_adjustment(self):
		if not self.asset or not flt(self.current_asset_value):
			return

		settings = frappe.get_single("Farm Settings")
		if not settings.default_asset_value_reduction_account:
			frappe.throw(
				_("Set the Default Asset Value Reduction Account in Farm Settings before selling culled birds.")
			)

		ava = frappe.get_doc({
			"doctype": "Asset Value Adjustment",
			"asset": self.asset,
			"date": self.sale_date,
			"current_asset_value": self.current_asset_value,
			"new_asset_value": self.new_asset_value,
			"difference_account": settings.default_asset_value_reduction_account,
			"cost_center": settings.default_cost_center,
		})
		ava.insert(ignore_permissions=True)
		ava.submit()
		self.db_set("asset_value_adjustment", ava.name)

	def cancel_asset_value_adjustment(self):
		if not self.asset_value_adjustment:
			return
		ava = frappe.get_doc("Asset Value Adjustment", self.asset_value_adjustment)
		if ava.docstatus == 1:
			ava.cancel()
