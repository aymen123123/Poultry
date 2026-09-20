import frappe
from frappe import _
from frappe.utils import flt


def make_maintenance_je(doc, method=None):
	"""Charge the actual cost entered on a completed Asset Maintenance Log to the
	shed's currently housed flock, tagged to the shed's cost center."""
	if doc.maintenance_status != "Completed" or not flt(doc.actual_maintenance_cost):
		return
	if not doc.poultry_shed:
		return

	settings = frappe.get_single("Farm Settings")
	if not settings.default_maintenance_expense_account:
		frappe.throw(_("Set the Default Equipment Maintenance Expense Account in Farm Settings first."))

	flock = frappe.db.get_value(
		"Poultry Flock",
		{"poultry_shed": doc.poultry_shed, "flock_status": ["in", ["نشط", "مرسمل"]]},
		["name", "flock_status"],
		as_dict=True,
	)
	if not flock:
		frappe.msgprint(
			_(
				"No active flock is currently housed in {0} — the maintenance cost was "
				"recorded but no allocation entry was made."
			).format(doc.poultry_shed)
		)
		return

	target_account = (
		settings.default_wip_flock_account
		if flock.flock_status == "نشط"
		else settings.default_feed_consumption_account
	)
	if not target_account:
		frappe.throw(_("Set the relevant default account in Farm Settings before posting."))

	cost_center = doc.cost_center or settings.default_cost_center

	je = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"posting_date": doc.completion_date or frappe.utils.today(),
		"company": frappe.db.get_single_value("Global Defaults", "default_company"),
		"user_remark": _("Equipment maintenance cost — {0} ({1})").format(doc.asset_name, doc.name),
		"accounts": [
			{
				"account": target_account,
				"debit_in_account_currency": doc.actual_maintenance_cost,
				"cost_center": cost_center,
				"reference_type": "Poultry Flock",
				"reference_name": flock.name,
			},
			{
				"account": settings.default_maintenance_expense_account,
				"credit_in_account_currency": doc.actual_maintenance_cost,
				"cost_center": cost_center,
			},
		],
	})
	je.insert(ignore_permissions=True)
	je.submit()
	frappe.db.set_value(doc.doctype, doc.name, "maintenance_journal_entry", je.name)


def cancel_maintenance_je(doc, method=None):
	if not doc.maintenance_journal_entry:
		return
	je = frappe.get_doc("Journal Entry", doc.maintenance_journal_entry)
	if je.docstatus == 1:
		je.cancel()
