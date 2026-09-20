import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, nowdate


class ShedCleaningDisinfection(Document):
	def validate(self):
		self.enforce_positive_swab_blocks_clearance()
		self.compute_downtime_days()

	def enforce_positive_swab_blocks_clearance(self):
		if self.swab_result == "موجب" and self.clearance_status == "معتمد للتسكين":
			frappe.throw(
				_("Swab result is positive. This shed cannot be cleared for restocking.")
			)

	def compute_downtime_days(self):
		end_date = self.clearance_date or nowdate()
		if self.depopulation_date:
			self.downtime_days = date_diff(end_date, self.depopulation_date)

	def on_submit(self):
		self.make_disinfectant_stock_entry()
		self.update_shed_status()
		self.make_cost_transfer_entry()

	def on_cancel(self):
		if self.stock_entry:
			stock_entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if stock_entry.docstatus == 1:
				stock_entry.cancel()
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.cancel()

	def make_disinfectant_stock_entry(self):
		if not (self.disinfectant_used and self.disinfectant_qty):
			return

		settings = frappe.get_single("Farm Settings")
		expense_account = settings.default_cd_expense_account
		if not expense_account:
			frappe.throw(
				_("Set Default Cleaning & Disinfection Expense Account in Farm Settings first.")
			)

		warehouse = frappe.db.get_value("Poultry Shed", self.shed, "linked_warehouse")
		if not warehouse:
			frappe.throw(_("Poultry Shed {0} has no Linked Warehouse set.").format(self.shed))

		stock_entry = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"posting_date": self.clearance_date or nowdate(),
			"items": [
				{
					"item_code": self.disinfectant_used,
					"qty": self.disinfectant_qty,
					"s_warehouse": warehouse,
					"expense_account": expense_account,
					"cost_center": settings.default_cost_center,
				}
			],
		})
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		self.db_set("stock_entry", stock_entry.name)

	def update_shed_status(self):
		status = "فارغ" if self.clearance_status == "معتمد للتسكين" else "تحت التطهير"
		frappe.db.set_value(
			"Poultry Shed",
			self.shed,
			{"shed_status": status, "last_cd_date": self.clearance_date or nowdate()},
		)

	def make_cost_transfer_entry(self):
		if not (self.charged_to_flock and self.total_cd_cost):
			return

		settings = frappe.get_single("Farm Settings")
		expense_account = settings.default_cd_expense_account
		wip_account = settings.default_wip_flock_account
		if not (expense_account and wip_account):
			frappe.throw(
				_(
					"Set Default Cleaning & Disinfection Expense Account and Default WIP Flock"
					" Account in Farm Settings before charging cost to a flock."
				)
			)

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": self.clearance_date or nowdate(),
			"company": frappe.db.get_single_value("Global Defaults", "default_company"),
			"user_remark": _("Cleaning & Disinfection cost {0} charged to {1}").format(
				self.name, self.charged_to_flock
			),
			"accounts": [
				{
					"account": wip_account,
					"debit_in_account_currency": self.total_cd_cost,
					"cost_center": settings.default_cost_center,
					"reference_type": "Poultry Flock",
					"reference_name": self.charged_to_flock,
				},
				{
					"account": expense_account,
					"credit_in_account_currency": self.total_cd_cost,
					"cost_center": settings.default_cost_center,
				},
			],
		})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)


def get_latest_cd_status(shed):
	"""Return the clearance_status of the most recent cleaning cycle for a shed,
	or None if the shed has never had one (fresh shed, nothing to clear)."""
	return frappe.db.get_value(
		"Shed Cleaning Disinfection",
		{"shed": shed, "docstatus": 1},
		"clearance_status",
		order_by="depopulation_date desc",
	)
