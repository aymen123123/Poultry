import frappe
from frappe import _
from frappe.utils import add_days, flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()

	if not filters.get("batch"):
		return columns, [], _("Select a Batch to trace."), None, []

	batch = frappe.get_doc("Batch", filters["batch"])
	window_start, window_end = get_source_window(batch)
	candidates = get_candidate_sources(window_start, window_end)

	data = get_forward_trace(batch.name)
	report_summary = get_report_summary(batch, window_start, window_end, candidates)

	message = None
	if len(candidates) > 1:
		message = _(
			"More than one shed/flock produced eggs in this batch's source window — "
			"narrow {0} in Farm Settings if this batch should map to a single flock."
		).format(frappe.bold(_("Egg Processing Lag (Days)")))

	return columns, data, message, None, report_summary


def get_columns():
	return [
		{"label": _("Source Doctype"), "fieldname": "doctype_name", "fieldtype": "Data", "width": 120},
		{"label": _("Document"), "fieldname": "document", "fieldtype": "Dynamic Link", "options": "doctype_name", "width": 140},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Qty Dispatched"), "fieldname": "qty", "fieldtype": "Float", "width": 120},
	]


def get_source_window(batch):
	window_end = batch.manufacturing_date or batch.expiry_date
	lag_days = frappe.db.get_single_value("Farm Settings", "egg_processing_lag_days") or 1
	window_start = add_days(window_end, -lag_days) if window_end else None
	return window_start, window_end


def get_candidate_sources(window_start, window_end):
	if not (window_start and window_end):
		return []
	return frappe.db.sql(
		"""
		select poultry_shed, poultry_flock, sum(total_eggs_collected) as eggs_collected
		from `tabDaily Shed Log`
		where log_date between %s and %s and docstatus=1
		group by poultry_shed, poultry_flock
		""",
		(window_start, window_end),
		as_dict=True,
	)


def get_feed_and_medication(flock, window_start, window_end):
	feed_rows = frappe.db.sql(
		"""
		select count(*) from `tabShed Feed Dispense`
		where poultry_flock=%s and dispense_date between %s and %s and docstatus=1
		""",
		(flock, window_start, window_end),
	)[0][0]

	medication_rows = frappe.get_all(
		"Medication Dispense",
		filters={
			"poultry_flock": flock,
			"docstatus": 1,
			"withdrawal_end_date": [">=", window_start],
			"dispense_date": ["<=", window_end],
		},
		fields=["name", "diagnosis", "withdrawal_end_date"],
	)
	return feed_rows or 0, medication_rows


def get_forward_trace(batch_no):
	rows = []
	for source_doctype, item_doctype in (
		("Sales Invoice", "Sales Invoice Item"),
		("Delivery Note", "Delivery Note Item"),
	):
		items = frappe.db.sql(
			f"""
			select parent, qty
			from `tab{item_doctype}`
			where batch_no=%s
			""",
			(batch_no,),
			as_dict=True,
		)
		for item in items:
			parent = frappe.db.get_value(
				source_doctype, item.parent, ["customer", "posting_date", "docstatus"], as_dict=True
			)
			if not parent or parent.docstatus != 1:
				continue
			rows.append({
				"doctype_name": source_doctype,
				"document": item.parent,
				"posting_date": parent.posting_date,
				"customer": parent.customer,
				"qty": flt(item.qty),
			})
	return rows


def get_report_summary(batch, window_start, window_end, candidates):
	withdrawal_flag = False
	shed_flock_labels = []
	for c in candidates:
		shed_flock_labels.append(f"{c.poultry_shed} ({c.poultry_flock})")
		_feed_count, meds = get_feed_and_medication(c.poultry_flock, window_start, window_end)
		if meds:
			withdrawal_flag = True

	return [
		{"label": _("Item"), "value": batch.item, "datatype": "Link", "options": "Item"},
		{"label": _("Manufacturing Date"), "value": frappe.utils.formatdate(batch.manufacturing_date), "datatype": "Data"},
		{"label": _("Expiry Date"), "value": frappe.utils.formatdate(batch.expiry_date) if batch.expiry_date else "-", "datatype": "Data"},
		{
			"label": _("Source Search Window"),
			"value": f"{frappe.utils.formatdate(window_start)} → {frappe.utils.formatdate(window_end)}",
			"datatype": "Data",
		},
		{
			"label": _("Candidate Sheds / Flocks"),
			"value": ", ".join(shed_flock_labels) or _("None found"),
			"datatype": "Data",
		},
		{
			"label": _("Active Medication Withdrawal in Window"),
			"value": _("Yes — check before recall clearance") if withdrawal_flag else _("None"),
			"datatype": "Data",
			"indicator": "red" if withdrawal_flag else "green",
		},
	]
