import frappe
from frappe.model.document import Document


class VaccinationPlan(Document):
	pass


@frappe.whitelist()
def generate_from_template(poultry_flock, template):
	"""Create one Vaccination Plan row per template entry, dated from the
	flock's receipt date plus that entry's age in weeks."""
	flock = frappe.get_doc("Poultry Flock", poultry_flock)
	protocol = frappe.get_doc("Vaccination Schedule Template", template)

	created = []
	for row in protocol.schedule:
		scheduled_date = frappe.utils.add_days(flock.receipt_date, row.age_week * 7)
		if frappe.db.exists(
			"Vaccination Plan",
			{
				"poultry_flock": poultry_flock,
				"vaccine_name": row.vaccine_name,
				"age_week": row.age_week,
			},
		):
			continue
		doc = frappe.get_doc({
			"doctype": "Vaccination Plan",
			"poultry_flock": poultry_flock,
			"vaccine_name": row.vaccine_name,
			"age_week": row.age_week,
			"scheduled_date": scheduled_date,
			"route": row.route,
		})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

	return created
