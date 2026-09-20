import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days


class MedicationDispense(Document):
	def validate(self):
		if self.withdrawal_period_days:
			self.withdrawal_end_date = add_days(self.dispense_date, self.withdrawal_period_days)
		else:
			self.withdrawal_end_date = None

	def on_submit(self):
		self.make_stock_entry()
		self.apply_withdrawal_hold()

	def on_cancel(self):
		self.cancel_stock_entry()
		self.clear_withdrawal_hold()

	def make_stock_entry(self):
		settings = frappe.get_single("Farm Settings")
		expense_account = settings.default_medication_expense_account
		if not expense_account:
			frappe.throw(
				_("Set Default Medication Expense Account in Farm Settings before dispensing medication.")
			)

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
				for row in self.medication_items
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name)

	def cancel_stock_entry(self):
		if not self.stock_entry:
			return
		stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
		if stock_entry.docstatus == 1:
			stock_entry.cancel()

	def apply_withdrawal_hold(self):
		if not self.withdrawal_end_date:
			return
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		# Extend, never shorten, an existing hold from an earlier treatment.
		current_hold = flock.withdrawal_hold_until
		if not current_hold or self.withdrawal_end_date > current_hold:
			flock.db_set("withdrawal_hold_until", self.withdrawal_end_date)

	def clear_withdrawal_hold(self):
		if not self.withdrawal_end_date:
			return
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		if flock.withdrawal_hold_until == self.withdrawal_end_date:
			flock.db_set("withdrawal_hold_until", None)
