import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class EggGrading(Document):
	def validate(self):
		total = sum(flt(row.qty) for row in self.grading_details or [])
		if flt(self.raw_qty) != total:
			frappe.throw(
				_("Raw Qty ({0}) must equal the sum of grade quantities ({1})").format(
					self.raw_qty, total
				)
			)

	def on_submit(self):
		self.make_repack_entry()

	def on_cancel(self):
		if not self.stock_entry:
			return
		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()

	def get_valuation_rate(self):
		rate = frappe.db.get_value(
			"Bin", {"item_code": self.raw_item, "warehouse": self.warehouse}, "valuation_rate"
		)
		rate = flt(rate)
		if rate <= 0:
			frappe.throw(
				_(
					"No valuation rate found for {0} in {1}. Receive some stock for this item"
					" in this warehouse before grading it."
				).format(self.raw_item, self.warehouse)
			)
		return rate

	def make_repack_entry(self):
		# Same per-unit cost is carried from the raw item to every graded output: an egg's
		# production cost does not change because it was sorted into a bigger or smaller bucket.
		rate = self.get_valuation_rate()

		items = [
			{
				"item_code": self.raw_item,
				"qty": self.raw_qty,
				"s_warehouse": self.warehouse,
				"basic_rate": rate,
			}
		]
		for row in self.grading_details:
			items.append({
				"item_code": row.item,
				"qty": row.qty,
				"t_warehouse": self.warehouse,
				"basic_rate": rate,
			})

		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"posting_date": self.grading_date,
			"items": items,
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name)
