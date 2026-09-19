import frappe
from frappe import _
from frappe.model.document import Document


class ShedFeedDispense(Document):
	def on_submit(self):
		self.make_stock_entry()

	def on_cancel(self):
		if not self.stock_entry:
			return
		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()

	def get_expense_account(self):
		"""WIP account while the flock is still rearing, feed consumption (COGS-side)
		account once it has been capitalized into production."""
		settings = frappe.get_single("Farm Settings")
		flock_status = frappe.db.get_value("Poultry Flock", self.poultry_flock, "flock_status")
		if flock_status == "مرسمل":
			account = settings.default_feed_consumption_account
		else:
			account = settings.default_wip_flock_account
		if not account:
			frappe.throw(
				_("Set the relevant default account in Farm Settings before dispensing feed.")
			)
		return account

	def make_stock_entry(self):
		settings = frappe.get_single("Farm Settings")
		expense_account = self.get_expense_account()

		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"posting_date": self.dispense_date,
			"items": [
				{
					"item_code": row.item,
					"qty": row.qty,
					"s_warehouse": self.source_warehouse,
					"expense_account": expense_account,
					"cost_center": settings.default_cost_center,
				}
				for row in self.feed_items
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name)
