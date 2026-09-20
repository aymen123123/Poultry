import frappe
from frappe import _
from frappe.model.document import Document


class PoultryFlock(Document):
	def validate(self):
		if self.is_new():
			self.check_shed_is_cleared()

	def check_shed_is_cleared(self):
		from poultry.poultry.doctype.shed_cleaning_disinfection.shed_cleaning_disinfection import (
			get_latest_cd_status,
		)

		status = get_latest_cd_status(self.poultry_shed)
		if status and status != "معتمد للتسكين":
			frappe.throw(
				_(
					"{0} is not cleared for restocking yet (latest Shed Cleaning &"
					" Disinfection status: {1}). Complete and clear the cleaning cycle first."
				).format(self.poultry_shed, status)
			)
