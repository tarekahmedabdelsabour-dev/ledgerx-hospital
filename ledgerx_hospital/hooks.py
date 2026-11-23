app_name = "ledgerx_hospital"
app_title = "Hospital"
app_publisher = "LedgerX"
app_description = "Clinics to hospital groups: appointments, inpatients, laboratory, radiology, theatre, emergency, pharmacy, insurance claims and doctor fees"
app_email = "hello@ledgerx.local"
app_license = "mit"

required_apps = ["erpnext"]

add_to_apps_screen = [
	{
		"name": "ledgerx_hospital",
		"logo": "/assets/ledgerx_hospital/images/hospital.svg",
		"title": "Hospital",
		"route": "/desk/hospital",
		"has_permission": "ledgerx_hospital.install.check_app_permission",
	}
]

scheduler_events = {
	"cron": {
		"*/15 * * * *": ["ledgerx_hospital.tasks.every_fifteen_minutes"],
		"15 0 * * *": ["ledgerx_hospital.tasks.daily"],
	},
}

from ledgerx_hospital import __version__ as _v  # noqa: E402

app_include_js = [f"/assets/ledgerx_hospital/js/hospital_forms.js?v={_v}"]

after_install = "ledgerx_hospital.install.after_install"
after_migrate = "ledgerx_hospital.install.after_migrate"
