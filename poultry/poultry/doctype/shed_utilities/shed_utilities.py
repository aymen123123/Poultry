import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ShedUtilities(Document):
	def validate(self):
		self.check_duplicate_period()
		self.compute_consumption_and_amounts()

	def check_duplicate_period(self):
		existing = frappe.db.exists(
			"Shed Utilities",
			{
				"poultry_shed": self.poultry_shed,
				"reading_month": self.reading_month,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_("Shed Utilities for {0} in {1} already exists: {2}").format(
					self.poultry_shed, self.reading_month, existing
				)
			)

	def compute_consumption_and_amounts(self):
		self.electricity_consumption_kwh = self.reading_diff(
			self.previous_electricity_reading, self.current_electricity_reading, "Electricity"
		)
		self.electricity_amount = flt(self.electricity_consumption_kwh) * flt(
			self.electricity_rate_per_kwh
		)

		self.water_consumption_m3 = self.reading_diff(
			self.previous_water_reading, self.current_water_reading, "Water"
		)
		self.water_amount = flt(self.water_consumption_m3) * flt(self.water_rate_per_m3)

		self.diesel_amount = flt(self.diesel_consumed_liters) * flt(self.diesel_rate_per_liter)

		self.total_utilities_cost = (
			flt(self.electricity_amount) + flt(self.water_amount) + flt(self.diesel_amount)
		)

	def reading_diff(self, previous, current, label):
		if not current:
			return 0
		previous = flt(previous)
		current = flt(current)
		if current < previous:
			frappe.throw(_("{0}: current reading cannot be less than the previous reading.").format(label))
		return current - previous

	def on_submit(self):
		self.make_allocation_je()

	def on_cancel(self):
		if not self.journal_entry:
			return
		je = frappe.get_doc("Journal Entry", self.journal_entry)
		if je.docstatus == 1:
			je.cancel()

	def get_current_flock(self):
		return frappe.db.get_value(
			"Poultry Flock",
			{"poultry_shed": self.poultry_shed, "flock_status": ["in", ["نشط", "مرسمل"]]},
			["name", "flock_status"],
			as_dict=True,
		)

	def make_allocation_je(self):
		if not flt(self.total_utilities_cost):
			return

		settings = frappe.get_single("Farm Settings")
		if not settings.default_utilities_expense_account:
			frappe.throw(_("Set the Default Utilities Expense Account in Farm Settings first."))

		flock = self.get_current_flock()
		if not flock:
			frappe.msgprint(
				_(
					"No active flock is currently housed in {0} — the actual utilities cost was "
					"recorded but no allocation entry was made."
				).format(self.poultry_shed)
			)
			return

		target_account = (
			settings.default_wip_flock_account
			if flock.flock_status == "نشط"
			else settings.default_feed_consumption_account
		)
		if not target_account:
			frappe.throw(_("Set the relevant default account in Farm Settings before posting."))

		cost_center = self.cost_center or settings.default_cost_center

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": self.reading_month,
			"company": frappe.db.get_single_value("Global Defaults", "default_company"),
			"user_remark": _("Actual shed utilities cost — {0} ({1})").format(
				self.poultry_shed, self.reading_month
			),
			"accounts": [
				{
					"account": target_account,
					"debit_in_account_currency": self.total_utilities_cost,
					"cost_center": cost_center,
					"reference_type": "Poultry Flock",
					"reference_name": flock.name,
				},
				{
					"account": settings.default_utilities_expense_account,
					"credit_in_account_currency": self.total_utilities_cost,
					"cost_center": cost_center,
				},
			],
		})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)
