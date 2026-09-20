frappe.views.calendar["Vaccination Plan"] = {
	field_map: {
		start: "scheduled_date",
		end: "scheduled_date",
		id: "name",
		title: "vaccine_name",
		allDay: "allDay",
		status: "status",
	},
	style_map: {
		"مجدول": "warning",
		"منفّذ": "success",
		"فائت": "danger",
	},
	get_events_method: "frappe.desk.calendar.get_events",
};
