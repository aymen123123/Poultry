import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt


class FlockCapitalization(Document):
	def validate(self):
		self.apply_farm_settings_defaults()
		self.check_capitalization_age()
		self.compute_cost_per_bird()

	def apply_farm_settings_defaults(self):
		settings = frappe.get_single("Farm Settings")
		if not self.wip_account:
			self.wip_account = settings.default_wip_flock_account
		if not self.target_account:
			self.target_account = settings.default_capitalization_account
		if not self.cost_center:
			self.cost_center = settings.default_cost_center

	def check_capitalization_age(self):
		settings = frappe.get_single("Farm Settings")
		min_age_week = settings.capitalization_age_week
		if not min_age_week:
			return

		receipt_date = frappe.db.get_value("Poultry Flock", self.poultry_flock, "receipt_date")
		if not receipt_date:
			return

		age_weeks = date_diff(self.capitalization_date, receipt_date) / 7
		if age_weeks < min_age_week:
			frappe.throw(
				_(
					"Flock {0} is only {1} weeks old. Capitalization Age (Week) in Farm Settings"
					" requires at least {2} weeks."
				).format(self.poultry_flock, round(age_weeks, 1), min_age_week)
			)

	def compute_cost_per_bird(self):
		if self.bird_qty:
			self.cost_per_bird = flt(self.capitalized_amount) / self.bird_qty

	def on_submit(self):
		self.make_journal_entry()
		self.update_flock()
		if self.asset_category:
			self.make_asset()

	def on_cancel(self):
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.cancel()
		if self.asset:
			asset = frappe.get_doc("Asset", self.asset)
			if asset.docstatus == 1:
				asset.cancel()
		self.revert_flock()

	def get_company(self):
		return frappe.db.get_single_value("Global Defaults", "default_company")

	def make_journal_entry(self):
		company = self.get_company()
		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"posting_date": self.capitalization_date,
			"company": company,
			"user_remark": _("Flock Capitalization {0} for {1}").format(self.name, self.poultry_flock),
			"accounts": [
				{
					"account": self.target_account,
					"debit_in_account_currency": self.capitalized_amount,
					"cost_center": self.cost_center,
				},
				{
					"account": self.wip_account,
					"credit_in_account_currency": self.capitalized_amount,
					"cost_center": self.cost_center,
				},
			],
		})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)

	def make_asset(self):
		company = self.get_company()
		asset = frappe.get_doc({
			"doctype": "Asset",
			"asset_name": _("Layer Flock - {0}").format(self.poultry_flock),
			"asset_category": self.asset_category,
			"company": company,
			"is_existing_asset": 1,
			"purchase_date": self.capitalization_date,
			"available_for_use_date": self.capitalization_date,
			"gross_purchase_amount": self.capitalized_amount,
			"asset_quantity": self.bird_qty or 1,
		})
		asset.insert(ignore_permissions=True)
		self.db_set("asset", asset.name)

	def update_flock(self):
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		flock.db_set("flock_status", "مرسمل")
		flock.db_set("capitalization_date", self.capitalization_date)

	def revert_flock(self):
		flock = frappe.get_doc("Poultry Flock", self.poultry_flock)
		flock.db_set("flock_status", "نشط")
		flock.db_set("capitalization_date", None)
