import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, today


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Flock"), "fieldname": "flock", "fieldtype": "Link", "options": "Poultry Flock", "width": 120},
		{"label": _("Age Week"), "fieldname": "age_week", "fieldtype": "Int", "width": 90},
		{"label": _("Actual Hen-Day %"), "fieldname": "actual_hen_day_pct", "fieldtype": "Percent", "width": 130},
		{"label": _("Std Hen-Day %"), "fieldname": "std_hen_day_pct", "fieldtype": "Percent", "width": 120},
		{"label": _("Hen-Day Deviation"), "fieldname": "hen_day_deviation", "fieldtype": "Percent", "width": 140},
		{"label": _("Actual Feed/Bird (week total)"), "fieldname": "actual_feed_per_bird", "fieldtype": "Float", "width": 170},
		{"label": _("Std Feed Intake (g/day)"), "fieldname": "std_feed_intake_g", "fieldtype": "Float", "width": 150},
		{"label": _("Actual Cum. Mortality %"), "fieldname": "actual_cum_mortality_pct", "fieldtype": "Percent", "width": 160},
		{"label": _("Std Cum. Mortality %"), "fieldname": "std_cum_mortality_pct", "fieldtype": "Percent", "width": 150},
	]


def get_data(filters):
	flock_filters = {"flock_status": ["in", ["نشط", "مرسمل"]]}
	if filters.get("poultry_flock"):
		flock_filters = {"name": filters["poultry_flock"]}

	flocks = frappe.get_all(
		"Poultry Flock",
		filters=flock_filters,
		fields=["name", "receipt_date", "breed", "initial_qty"],
	)

	rows = []
	for flock in flocks:
		if not flock.breed:
			continue
		standards = frappe.get_all(
			"Weekly Standard",
			filters={"parent": flock.breed, "parenttype": "Breed Standard", "parentfield": "weekly_standards"},
			fields=["age_week", "std_hen_day_pct", "std_feed_intake_g", "std_cum_mortality_pct"],
			order_by="age_week asc",
		)
		current_age_week = max(date_diff(today(), flock.receipt_date) // 7, 0)

		for std in standards:
			if std.age_week > current_age_week:
				continue
			week_start = add_days(flock.receipt_date, (std.age_week - 1) * 7)
			week_end = add_days(flock.receipt_date, std.age_week * 7 - 1)

			actual_hen_day = frappe.db.sql(
				"""
				select avg(hen_day_pct) from `tabDaily Shed Log`
				where poultry_flock=%s and log_date between %s and %s and docstatus=1
				""",
				(flock.name, week_start, week_end),
			)[0][0]

			feed_qty = frappe.db.sql(
				"""
				select sum(fdd.qty)
				from `tabShed Feed Dispense` sfd
				join `tabFeed Dispense Detail` fdd on fdd.parent = sfd.name
				where sfd.poultry_flock=%s and sfd.dispense_date between %s and %s and sfd.docstatus=1
				""",
				(flock.name, week_start, week_end),
			)[0][0]

			mortality_to_date = frappe.db.sql(
				"""
				select sum(mortality_qty + culling_qty) from `tabDaily Shed Log`
				where poultry_flock=%s and log_date <= %s and docstatus=1
				""",
				(flock.name, week_end),
			)[0][0]

			actual_cum_mortality_pct = (
				flt(mortality_to_date) / flock.initial_qty * 100 if flock.initial_qty else None
			)
			actual_feed_per_bird = flt(feed_qty) / flock.initial_qty if flock.initial_qty else None
			hen_day_deviation = (
				actual_hen_day - std.std_hen_day_pct
				if (actual_hen_day is not None and std.std_hen_day_pct is not None)
				else None
			)

			rows.append({
				"flock": flock.name,
				"age_week": std.age_week,
				"actual_hen_day_pct": actual_hen_day,
				"std_hen_day_pct": std.std_hen_day_pct,
				"hen_day_deviation": hen_day_deviation,
				"actual_feed_per_bird": actual_feed_per_bird,
				"std_feed_intake_g": std.std_feed_intake_g,
				"actual_cum_mortality_pct": actual_cum_mortality_pct,
				"std_cum_mortality_pct": std.std_cum_mortality_pct,
			})

	return rows
