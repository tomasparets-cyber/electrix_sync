frappe.pages["planning-calendar"].on_page_load = function (wrapper) {
	new ElectrixPlanningCalendar(wrapper);
};

class ElectrixPlanningCalendar {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Calendario de planificación"), single_column: true });
		this.startDate = this.startOfWeek(frappe.datetime.get_today());
		this.page.add_inner_button(__("Tabla"), () => frappe.set_route("planning"));
		this.page.add_inner_button(__("Anterior"), () => this.shift(-7));
		this.page.add_inner_button(__("Hoy"), () => { this.startDate = this.startOfWeek(frappe.datetime.get_today()); this.load(); });
		this.page.add_inner_button(__("Siguiente"), () => this.shift(7));
		this.page.set_primary_action(__("Actualizar"), () => this.load(), "refresh");
		this.load();
	}

	startOfWeek(value) {
		const date = new Date(`${value}T12:00:00`);
		return frappe.datetime.add_days(value, -((date.getDay() + 6) % 7));
	}

	shift(days) { this.startDate = frappe.datetime.add_days(this.startDate, days); this.load(); }

	async load() {
		this.page.main.html(`<div class="planning-loading">${__("Cargando calendario…")}</div>`);
		const response = await frappe.call({ method: "electrix_sync.api.planning.get_board", args: { start_date: this.startDate, days: 7 } });
		this.data = response.message;
		this.render();
	}

	render() {
		const employees = this.data.employees.filter((row) => row.custom_stel_calendar_id);
		const employeeById = Object.fromEntries(employees.map((row) => [row.name, row]));
		const filters = employees.map((row) => `<label><input type="checkbox" data-employee="${row.name}" checked> ${frappe.utils.escape_html(row.employee_name)}</label>`).join("");
		const headers = this.data.days.map((day) => `<div class="pc-day-header"><strong>${this.weekday(day)}</strong><span>${frappe.datetime.str_to_user(day)}</span></div>`).join("");
		const dayColumns = this.data.days.map((day) => `<div class="pc-day" data-day="${day}">${this.eventsForDay(day, employeeById)}</div>`).join("");
		const hours = Array.from({ length: 24 }, (_, hour) => `<div class="pc-hour">${String(hour).padStart(2, "0")}:00</div>`).join("");
		this.page.main.html(`<div class="pc-shell"><aside class="pc-filters"><strong>${__("Calendarios")}</strong><button class="btn btn-xs btn-default pc-all">${__("Mostrar todos")}</button>${filters}</aside><section class="pc-calendar"><div class="pc-header"><div></div>${headers}</div><div class="pc-body"><div class="pc-hours">${hours}</div>${dayColumns}</div></section></div>`);
		this.bind();
	}

	eventsForDay(day, employeeById) {
		const cards = [];
		for (const event of this.data.events.filter((row) => (row.starts_on || "").slice(0, 10) === day)) {
			const employees = event.assigned_employees || [];
			employees.forEach((employee, index) => {
				if (!employeeById[employee]) return;
				const start = this.minutes(event.starts_on);
				const end = Math.max(this.minutes(event.ends_on), start + 15);
				const top = start * 0.8;
				const height = Math.max((end - start) * 0.8, 20);
				const width = 94 / Math.max(employees.length, 1);
				cards.push(`<button class="pc-event" data-employee="${employee}" data-event="${event.name}" style="top:${top}px;height:${height}px;left:${2 + index * width}%;width:${width - 1}%"><strong>${frappe.utils.escape_html(event.subject || event.name)}</strong><span>${this.time(event.starts_on)}–${this.time(event.ends_on)}</span><small>${frappe.utils.escape_html(employeeById[employee].employee_name)}</small></button>`);
			});
		}
		return cards.join("");
	}

	bind() {
		this.page.main.find(".pc-filters input").on("change", () => this.applyFilters());
		this.page.main.find(".pc-all").on("click", () => { this.page.main.find(".pc-filters input").prop("checked", true); this.applyFilters(); });
		this.page.main.find(".pc-event").on("click", (event) => frappe.set_route("Form", "Event", event.currentTarget.dataset.event));
	}

	applyFilters() {
		const visible = new Set(this.page.main.find(".pc-filters input:checked").map((_, input) => input.dataset.employee).get());
		this.page.main.find(".pc-event").each((_, card) => { card.style.display = visible.has(card.dataset.employee) ? "" : "none"; });
	}

	minutes(value) { const time = (value || "").slice(11, 16).split(":").map(Number); return (time[0] || 0) * 60 + (time[1] || 0); }
	time(value) { return (value || "").slice(11, 16); }
	weekday(day) { return new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short" }).format(new Date(`${day}T12:00:00`)); }
}
