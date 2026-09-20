import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class DailyShedLog(Document):
	def validate(self):
		self.compute_egg_totals()
		self.warn_if_under_withdrawal_hold()

	def compute_egg_totals(self):
		self.total_eggs_collected = sum(flt(row.qty) for row in self.egg_collection or [])
		flock_qty = frappe.db.get_value("Poultry Flock", self.poultry_flock, "current_qty")
		self.hen_day_pct = (self.total_eggs_collected / flock_qty * 100) if flock_qty else 0

	def warn_if_under_withdrawal_hold(self):
		if not self.egg_collection:
			return
		hold_until = frappe.db.get_value("Poultry Flock", self.poultry_flock, "withdrawal_hold_until")
		if hold_until and self.log_date <= hold_until:
			frappe.msgprint(
				_(
					"{0} is still under a medication withdrawal hold until {1}. Eggs collected"
					" today must not be sold or delivered to customers."
				).format(self.poultry_flock, hold_until),
				indicator="orange",
				alert=True,
			)

	def on_submit(self):
		self.update_flock_count()
		self.make_egg_stock_entry()

	def on_cancel(self):
		self.reverse_flock_count()
		self.cancel_egg_stock_entry()

	def update_flock_count(self):
		reduction = (self.mortality_qty or 0) + (self.culling_qty or 0)
		if not reduction:
			return
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		new_qty = (flock.current_qty or 0) - reduction
		if new_qty < 0:
			frappe.throw(
				_("Mortality + culling ({0}) exceeds current flock qty ({1}) for {2}").format(
					reduction, flock.current_qty, flock.name
				)
			)
		flock.db_set("current_qty", new_qty)

	def reverse_flock_count(self):
		reduction = (self.mortality_qty or 0) + (self.culling_qty or 0)
		if not reduction:
			return
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		flock.db_set("current_qty", (flock.current_qty or 0) + reduction)

	def make_egg_stock_entry(self):
		if not self.egg_collection:
			return

		warehouse = frappe.db.get_value("Poultry Shed", self.poultry_shed, "linked_warehouse")
		if not warehouse:
			frappe.throw(
				_("Poultry Shed {0} has no Linked Warehouse set. Cannot record egg stock.").format(
					self.poultry_shed
				)
			)

		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"posting_date": self.log_date,
			"items": [
				{
					"item_code": row.item,
					"qty": row.qty,
					"t_warehouse": warehouse,
				}
				for row in self.egg_collection
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name)

	def cancel_egg_stock_entry(self):
		if not self.stock_entry:
			return
		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()
