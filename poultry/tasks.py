import frappe
from frappe import _
from frappe.utils import flt, today


def daily_cost_run():
	"""Nightly job: aggregate feed, flock depreciation, and each flock's share of
	shared utilities/labor into a Daily Cost Run Result per active/production
	flock, posting a Journal Entry for the utilities/labor share."""
	run_date = today()
	settings = frappe.get_single("Farm Settings")

	flocks = frappe.get_all(
		"Poultry Flock",
		filters={"flock_status": ["in", ["نشط", "مرسمل"]]},
		fields=["name", "flock_status", "current_qty"],
	)
	if not flocks:
		return

	feed_cost_by_flock = get_feed_cost_by_flock(run_date)
	depreciation_by_flock = get_depreciation_by_flock(run_date, flocks)

	utilities_pool = get_daily_expense(run_date, settings.default_utilities_expense_account)
	labor_pool = get_daily_expense(run_date, settings.default_labor_expense_account)

	weights = get_allocation_weights(flocks, settings.cost_allocation_basis)
	total_weight = sum(weights.values()) or 1

	for flock in flocks:
		if frappe.db.exists(
			"Daily Cost Run Result", {"poultry_flock": flock.name, "log_date": run_date}
		):
			continue

		share = flt(weights.get(flock.name, 0)) / total_weight if total_weight else 0
		allocated_utilities = flt(utilities_pool) * share
		allocated_labor = flt(labor_pool) * share
		feed_cost = flt(feed_cost_by_flock.get(flock.name))
		depreciation_cost = flt(depreciation_by_flock.get(flock.name))
		total_cost = feed_cost + depreciation_cost + allocated_utilities + allocated_labor

		eggs_collected = get_eggs_collected(flock.name, run_date)
		cost_per_egg = (total_cost / eggs_collected) if eggs_collected else 0

		je_name = make_allocation_je(
			flock, settings, allocated_utilities, allocated_labor, run_date
		)

		frappe.get_doc({
			"doctype": "Daily Cost Run Result",
			"log_date": run_date,
			"poultry_flock": flock.name,
			"feed_cost": feed_cost,
			"depreciation_cost": depreciation_cost,
			"allocated_utilities_cost": allocated_utilities,
			"allocated_labor_cost": allocated_labor,
			"total_cost": total_cost,
			"eggs_collected": eggs_collected,
			"cost_per_egg": cost_per_egg,
			"cost_per_carton30": cost_per_egg * 30,
			"journal_entry": je_name,
		}).insert(ignore_permissions=True)

	frappe.db.commit()


def get_feed_cost_by_flock(run_date):
	rows = frappe.get_all(
		"Shed Feed Dispense",
		filters={"dispense_date": run_date, "docstatus": 1},
		fields=["poultry_flock", "stock_entry"],
	)
	result = {}
	for row in rows:
		if not row.stock_entry:
			continue
		value = frappe.db.get_value("Stock Entry", row.stock_entry, "total_outgoing_value")
		result[row.poultry_flock] = flt(result.get(row.poultry_flock)) + flt(value)
	return result


def get_depreciation_by_flock(run_date, flocks):
	result = {}
	for flock in flocks:
		asset = frappe.db.get_value(
			"Flock Capitalization", {"poultry_flock": flock.name, "docstatus": 1}, "asset"
		)
		if not asset:
			continue
		schedule_parent = frappe.db.get_value(
			"Asset Depreciation Schedule", {"asset": asset, "docstatus": 1}, "name"
		)
		if not schedule_parent:
			continue
		amount = frappe.db.sql(
			"""
			select sum(depreciation_amount) from `tabDepreciation Schedule`
			where parent=%s and schedule_date=%s and journal_entry is not null
			""",
			(schedule_parent, run_date),
		)[0][0]
		if amount:
			result[flock.name] = flt(amount)
	return result


def get_daily_expense(run_date, account):
	if not account:
		return 0
	total = frappe.db.sql(
		"""
		select sum(debit) - sum(credit) from `tabGL Entry`
		where account=%s and posting_date=%s and is_cancelled=0
		""",
		(account, run_date),
	)[0][0]
	return flt(total)


def get_allocation_weights(flocks, basis):
	if basis == "توزيع متساوٍ":
		return {f.name: 1 for f in flocks}
	return {f.name: flt(f.current_qty) for f in flocks}


def get_eggs_collected(flock, run_date):
	total = frappe.db.sql(
		"""
		select sum(total_eggs_collected) from `tabDaily Shed Log`
		where poultry_flock=%s and log_date=%s and docstatus=1
		""",
		(flock, run_date),
	)[0][0]
	return int(total or 0)


def make_allocation_je(flock, settings, utilities_amount, labor_amount, run_date):
	target_account = (
		settings.default_wip_flock_account
		if flock.flock_status == "نشط"
		else settings.default_feed_consumption_account
	)
	if not target_account:
		return None

	accounts = []
	total_amount = 0
	if utilities_amount and settings.default_utilities_expense_account:
		accounts.append({
			"account": settings.default_utilities_expense_account,
			"credit_in_account_currency": utilities_amount,
			"cost_center": settings.default_cost_center,
		})
		total_amount += utilities_amount
	if labor_amount and settings.default_labor_expense_account:
		accounts.append({
			"account": settings.default_labor_expense_account,
			"credit_in_account_currency": labor_amount,
			"cost_center": settings.default_cost_center,
		})
		total_amount += labor_amount
	if not total_amount:
		return None

	accounts.insert(0, {
		"account": target_account,
		"debit_in_account_currency": total_amount,
		"cost_center": settings.default_cost_center,
		"reference_type": "Poultry Flock",
		"reference_name": flock.name,
	})

	je = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"posting_date": run_date,
		"company": frappe.db.get_single_value("Global Defaults", "default_company"),
		"user_remark": _(
			"Daily cost run - shared utilities/labor allocation for {0}"
		).format(flock.name),
		"accounts": accounts,
	})
	je.insert(ignore_permissions=True)
	je.submit()
	return je.name
