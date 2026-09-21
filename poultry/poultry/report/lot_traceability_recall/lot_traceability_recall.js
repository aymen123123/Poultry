frappe.query_reports["Lot Traceability & Recall"] = {
	filters: [
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
			reqd: 1,
		},
	],
};
