frappe.pages["planning-calendar"].on_page_load = function (wrapper) {
	new ElectrixPlanningCalendar(wrapper);
};

class ElectrixPlanningCalendar {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Calendario de planificación"), single_column: true });
		this.ensureComponentStyles();
		this.startDate = this.startOfWeek(frappe.datetime.get_today());
		this.visibleEmployees = new Set();
		this.backlogCollapsed = window.localStorage.getItem("electrix-planning-backlog-collapsed") === "1";
		this.page.add_inner_button(__("Anterior"), () => this.shift(-7));
		this.page.add_inner_button(__("Hoy"), () => { this.startDate = this.startOfWeek(frappe.datetime.get_today()); this.load(); });
		this.page.add_inner_button(__("Siguiente"), () => this.shift(7));
		this.addCalendarMenu();
		this.page.set_primary_action(__("Actualizar"), () => this.load(), "refresh");
		this.load();
	}

	ensureComponentStyles() {
		if (document.getElementById("electrix-planning-calendar-actions-style")) return;
		$(document.head).append(`<style id="electrix-planning-calendar-actions-style">
			.pc-planning-shell { display:grid !important; grid-template-columns:minmax(0,1fr) 320px !important; gap:18px !important; height:calc(100vh - 190px) !important; min-height:480px !important; overflow:hidden !important; transition:grid-template-columns .2s ease !important; }
			.pc-planning-shell.is-backlog-collapsed { grid-template-columns:minmax(0,1fr) 42px !important; }
			.pc-planning-shell .planning-backlog { min-height:0 !important; overflow:hidden !important; }
			.pc-planning-shell .planning-backlog-list { min-height:0; flex:1; overflow-y:auto !important; }
			.planning-backlog-title { display:flex !important; align-items:center !important; justify-content:space-between !important; gap:8px !important; }
			.planning-backlog-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; min-width:0; flex:1; }
			.planning-backlog-toggle { width:28px !important; min-width:28px !important; height:28px !important; padding:0 !important; display:flex !important; align-items:center !important; justify-content:center !important; border:0 !important; border-radius:6px !important; background:transparent !important; color:var(--text-muted) !important; box-shadow:none !important; }
			.planning-backlog-toggle:hover,.planning-backlog-toggle:focus { background:var(--control-bg) !important; color:var(--text-color) !important; }
			.is-backlog-collapsed .planning-backlog { padding:6px !important; }
			.is-backlog-collapsed .planning-backlog-heading,.is-backlog-collapsed .planning-search,.is-backlog-collapsed .planning-backlog-list { display:none !important; }
			.is-backlog-collapsed .planning-backlog-title { justify-content:center !important; margin:0 !important; }
			@media (max-width:1100px) { .pc-planning-shell { grid-template-columns:minmax(0,1fr) min(300px,38vw) !important; } .pc-planning-shell.is-backlog-collapsed { grid-template-columns:minmax(0,1fr) 42px !important; } }
			.pc-event > button.pc-actions-toggle {
				position:absolute !important; inset:3px 3px auto auto !important;
				width:22px !important; min-width:22px !important; max-width:22px !important;
				height:22px !important; min-height:22px !important; margin:0 !important;
				padding:0 !important; display:flex !important; align-items:center !important;
				justify-content:center !important; border:0 !important; border-radius:4px !important;
				background:transparent !important; box-shadow:none !important; color:var(--text-muted) !important;
				font-size:14px !important; line-height:1 !important; opacity:.8; z-index:5;
			}
			.pc-event > button.pc-actions-toggle:hover,
			.pc-event > button.pc-actions-toggle:focus { opacity:1; background:var(--control-bg) !important; }
			body > .pc-event-actions-menu {
				position:fixed !important; display:block !important; z-index:1060 !important;
				min-width:160px !important; width:auto !important; margin:0 !important; padding:5px !important;
				border:1px solid var(--border-color) !important; border-radius:8px !important;
				background:var(--card-bg) !important; box-shadow:0 8px 24px rgba(0,0,0,.16) !important;
			}
			body > .pc-event-actions-menu > button {
				position:static !important; width:100% !important; min-width:0 !important; height:auto !important;
				display:flex !important; align-items:center !important; gap:8px !important;
				margin:0 !important; padding:7px 9px !important; border:0 !important; border-radius:5px !important;
				background:transparent !important; box-shadow:none !important; color:var(--text-color) !important;
				justify-content:flex-start !important; text-align:left !important;
			}
			body > .pc-event-actions-menu > button > span { flex:1; text-align:left !important; }
			body > .pc-event-actions-menu > button:hover,
			body > .pc-event-actions-menu > button:focus { background:var(--subtle-fg) !important; }
		</style>`);
	}

	addCalendarMenu() {
		this.calendarOptions = this.page.add_custom_button_group(__("Calendarios"), "calendar");
		this.calendarOptions.addClass("pc-calendar-options dropdown-menu-right");
		this.calendarMenu = this.calendarOptions.closest(".custom-btn-group").addClass("pc-calendar-menu");
		this.calendarOptions.on("click", (event) => event.stopPropagation());
	}

	startOfWeek(value) {
		const date = new Date(`${value}T12:00:00`);
		return frappe.datetime.add_days(value, -((date.getDay() + 6) % 7));
	}

	shift(days) { this.startDate = frappe.datetime.add_days(this.startDate, days); this.load(); }

	async load() {
		this.closeActionsMenu();
		this.page.main.html(`<div class="planning-loading">${__("Cargando calendario…")}</div>`);
		const response = await frappe.call({ method: "electrix_sync.api.planning.get_board", args: { start_date: this.startDate, days: 7 } });
		this.data = response.message;
		this.employees = this.data.employees.filter((row) => row.custom_stel_calendar_id);
		if (!this.filtersInitialized) {
			this.employees.forEach((row) => this.visibleEmployees.add(row.name));
			this.filtersInitialized = true;
		}
		this.renderCalendarMenu();
		this.render();
	}

	renderCalendarMenu() {
		const rows = this.employees.map((row) => `<label class="dropdown-item pc-calendar-option">
			<input type="checkbox" data-employee="${row.name}" ${this.visibleEmployees.has(row.name) ? "checked" : ""}>
			<span>${frappe.utils.escape_html(row.employee_name)}</span>
		</label>`).join("");
		this.calendarOptions.html(`<div class="pc-calendar-actions">
			<button class="btn btn-xs btn-default pc-select-all">${__("Todos")}</button>
			<button class="btn btn-xs btn-default pc-select-none">${__("Ninguno")}</button>
		</div>${rows || `<div class="dropdown-item text-muted">${__("No hay calendarios")}</div>`}`);
		this.calendarMenu.find("input").on("change", (event) => {
			const employee = event.currentTarget.dataset.employee;
			event.currentTarget.checked ? this.visibleEmployees.add(employee) : this.visibleEmployees.delete(employee);
			this.applyFilters();
		});
		this.calendarMenu.find(".pc-select-all").on("click", () => {
			this.employees.forEach((row) => this.visibleEmployees.add(row.name)); this.renderCalendarMenu(); this.applyFilters();
		});
		this.calendarMenu.find(".pc-select-none").on("click", () => {
			this.visibleEmployees.clear(); this.renderCalendarMenu(); this.applyFilters();
		});
	}

	render() {
		this.didManipulate = false;
		this.dragged = null;
		this.employeeById = Object.fromEntries(this.employees.map((row) => [row.name, row]));
		const headers = this.data.days.map((day) => `<div class="pc-day-header"><strong>${this.weekday(day)}</strong><span>${frappe.datetime.str_to_user(day)}</span></div>`).join("");
		const dayColumns = this.data.days.map((day) => `<div class="pc-day" data-day="${day}">${this.eventsForDay(day)}</div>`).join("");
		const hours = Array.from({ length: 24 }, (_, hour) => `<div class="pc-hour">${String(hour).padStart(2, "0")}:00</div>`).join("");
		const unplanned = this.data.unplanned.map((event) => this.backlogCard(event)).join("");
		this.page.main.html(`<div class="pc-planning-shell ${this.backlogCollapsed ? "is-backlog-collapsed" : ""}">
			<section class="pc-calendar"><div class="pc-header"><div></div>${headers}</div><div class="pc-body"><div class="pc-hours">${hours}</div>${dayColumns}</div></section>
			<aside class="planning-backlog">
				<div class="planning-backlog-title"><div class="planning-backlog-heading"><strong>${__("Sin planificar")}</strong><span>${this.data.unplanned.length}</span></div><button type="button" class="planning-backlog-toggle" title="${this.backlogCollapsed ? __("Mostrar panel") : __("Ocultar panel")}" aria-label="${this.backlogCollapsed ? __("Mostrar panel Sin planificar") : __("Ocultar panel Sin planificar")}" aria-expanded="${!this.backlogCollapsed}">${frappe.utils.icon(this.backlogCollapsed ? "chevron-left" : "chevron-right", "sm")}</button></div>
				<input class="form-control planning-search" placeholder="${__("Buscar")}">
				<div class="planning-backlog-list">${unplanned || `<div class="planning-empty">${__("No hay eventos pendientes")}</div>`}</div>
			</aside>
		</div>`);
		this.bind();
		this.applyFilters();
	}

	backlogCard(event) {
		const duration = Number(event.custom_estimated_duration || 1).toFixed(1).replace(".0", "");
		return `<article class="planning-event ${this.eventStatusClass(event)} is-backlog pc-backlog-event" style="${this.eventStatusStyle(event)}" draggable="true" data-event="${event.name}" data-search="${frappe.utils.escape_html((event.subject || "").toLowerCase())}">
			<button type="button" class="pc-actions-toggle" title="${__("Acciones")}" aria-label="${__("Acciones del evento")}" aria-expanded="false"><span aria-hidden="true">▾</span></button>
			<strong>${frappe.utils.escape_html(event.subject || event.name)}</strong>
			<span>${frappe.utils.escape_html([event.event_category, event.status || "Open"].filter(Boolean).join(" · "))}</span>
			<small>${duration}h</small>
		</article>`;
	}

	eventsForDay(day) {
		const cards = [];
		for (const event of this.data.events.filter((row) => (row.starts_on || "").slice(0, 10) === day)) {
			const syncWarning = ["Error", "Conflict", "Pending"].includes(event.custom_stel_sync_status) ? event.custom_stel_sync_status : null;
			const employees = event.assigned_employees || [];
			employees.forEach((employee, index) => {
				if (!this.employeeById[employee]) return;
				const start = this.minutes(event.starts_on);
				const end = Math.max(this.minutes(event.ends_on), start + 15);
				const top = start * 0.8;
				const height = Math.max((end - start) * 0.8, 20);
				const width = 94 / Math.max(employees.length, 1);
				cards.push(`<div class="pc-event ${this.eventStatusClass(event)} ${syncWarning ? "has-sync-warning" : ""}" data-employee="${employee}" data-event="${event.name}" data-start="${event.starts_on}" data-end="${event.ends_on}" style="top:${top}px;height:${height}px;left:${2 + index * width}%;width:${width - 1}%;${this.eventStatusStyle(event, syncWarning)}">
					<button type="button" class="pc-actions-toggle" title="${__("Acciones")}" aria-label="${__("Acciones del evento")}" aria-expanded="false"><span aria-hidden="true">▾</span></button><strong>${frappe.utils.escape_html(event.subject || event.name)}</strong><span>${this.time(event.starts_on)}–${this.time(event.ends_on)}</span><small>${frappe.utils.escape_html(this.employeeById[employee].employee_name)}${syncWarning ? ` · STEL: ${syncWarning}` : ""}</small><i class="pc-resize" title="${__("Cambiar duración")}"></i>
				</div>`);
			});
		}
		return cards.join("");
	}

	eventStatusClass(event) {
		const status = String(event.status || "Open").trim().toLowerCase();
		if (["closed", "completed"].includes(status) || event.custom_planning_status === "Completed") {
			return "is-status-completed";
		}
		if (status === "cancelled" || status === "canceled") {
			return "is-status-cancelled";
		}
		return "is-status-open";
	}

	eventStatusStyle(event, syncWarning = null) {
		if (syncWarning) {
			return "background-color:var(--orange-50,#fff3e0);border-left-color:var(--orange-500,#e86c13)";
		}
		const statusClass = this.eventStatusClass(event);
		if (statusClass === "is-status-completed") {
			return "background-color:var(--green-100,#d9f2e3);border-left-color:var(--green-500,#28a745)";
		}
		if (statusClass === "is-status-cancelled") {
			return "background-color:var(--red-100,#fce0e0);border-left-color:var(--red-500,#e24c4c)";
		}
		return "background-color:var(--blue-100,#e7f1ff);border-left-color:var(--blue-500,#2490ef)";
	}

	bind() {
		this.page.main.find(".pc-event").on("pointerdown", (event) => {
			if ($(event.target).closest(".pc-resize,.pc-actions-toggle").length) return;
			this.startMove(event);
		});
		this.page.main.find(".pc-event").on("click", (event) => {
			if (this.didManipulate) { this.didManipulate = false; return; }
			this.editEvent(event.currentTarget.dataset.event);
		});
		this.page.main.find(".pc-resize").on("pointerdown", (event) => this.startResize(event));
		this.page.main.find(".pc-actions-toggle").on("click", (event) => this.showActionsMenu(event));
		this.page.main.find(".planning-backlog-toggle").on("click", () => this.toggleBacklog());
		this.page.main.find(".pc-day").on("click", (event) => {
			if (event.target !== event.currentTarget) return;
			const rect = event.currentTarget.getBoundingClientRect();
			this.createAt(event.currentTarget.dataset.day, this.snapMinutes((event.originalEvent.clientY - rect.top) / 0.8));
		}).on("dragover", (event) => {
			event.preventDefault();
			event.currentTarget.classList.add("is-over");
		}).on("dragleave", (event) => event.currentTarget.classList.remove("is-over"))
			.on("drop", (event) => this.dropUnplanned(event));
		this.page.main.find(".pc-backlog-event").on("dragstart", (event) => {
			event.originalEvent.dataTransfer.setData("text/plain", event.currentTarget.dataset.event);
		}).on("click", (event) => {
			if ($(event.target).closest(".pc-actions-toggle").length) return;
			this.editEvent(event.currentTarget.dataset.event);
		});
		this.page.main.find(".planning-search").on("input", (event) => {
			const value = event.currentTarget.value.toLowerCase();
			this.page.main.find(".pc-backlog-event").each((_, card) => {
				card.style.display = card.dataset.search.includes(value) ? "" : "none";
			});
		});
	}

	toggleBacklog() {
		this.backlogCollapsed = !this.backlogCollapsed;
		window.localStorage.setItem("electrix-planning-backlog-collapsed", this.backlogCollapsed ? "1" : "0");
		this.page.main.find(".pc-planning-shell").toggleClass("is-backlog-collapsed", this.backlogCollapsed);
		const button = this.page.main.find(".planning-backlog-toggle");
		button.html(frappe.utils.icon(this.backlogCollapsed ? "chevron-left" : "chevron-right", "sm"))
			.attr("aria-expanded", String(!this.backlogCollapsed))
			.attr("aria-label", this.backlogCollapsed ? __("Mostrar panel Sin planificar") : __("Ocultar panel Sin planificar"))
			.attr("title", this.backlogCollapsed ? __("Mostrar panel") : __("Ocultar panel"));
	}

	startMove(event) {
		event.preventDefault();
		const card = event.currentTarget;
		const originX = event.originalEvent.clientX;
		const originY = event.originalEvent.clientY;
		const grabOffsetMinutes = Math.max(0, (originY - card.getBoundingClientRect().top) / 0.8);
		const duration = Math.max(this.datetimeMinutes(card.dataset.end) - this.datetimeMinutes(card.dataset.start), 15);
		this.didManipulate = false;
		card.classList.add("is-moving");
		const move = (pointerEvent) => {
			if (Math.abs(pointerEvent.clientX - originX) + Math.abs(pointerEvent.clientY - originY) > 4) this.didManipulate = true;
			const snappedDelta = this.snapDuration((pointerEvent.clientY - originY) / 0.8);
			card.style.transform = `translate(${pointerEvent.clientX - originX}px, ${snappedDelta * 0.8}px)`;
		};
		const up = async (pointerEvent) => {
			document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up);
			card.classList.remove("is-moving"); card.style.transform = "";
			if (!this.didManipulate) return;
			const dayColumn = document.elementFromPoint(pointerEvent.clientX, pointerEvent.clientY)?.closest(".pc-day");
			if (!dayColumn) return;
			const rect = dayColumn.getBoundingClientRect();
			const minutes = this.snapMinutes((pointerEvent.clientY - rect.top) / 0.8 - grabOffsetMinutes);
			await this.persistTime(card.dataset.event, this.dateTime(dayColumn.dataset.day, minutes), this.dateTime(dayColumn.dataset.day, minutes + duration));
		};
		document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, { once: true });
	}

	startResize(event) {
		event.preventDefault(); event.stopPropagation();
		const card = event.currentTarget.closest(".pc-event");
		const originY = event.originalEvent.clientY;
		const originalDuration = Math.max(this.datetimeMinutes(card.dataset.end) - this.datetimeMinutes(card.dataset.start), 15);
		this.didManipulate = true;
		const move = (pointerEvent) => {
			const duration = Math.max(15, this.snapDuration(originalDuration + (pointerEvent.clientY - originY) / 0.8));
			card.style.height = `${duration * 0.8}px`;
			card.dataset.previewDuration = duration;
		};
		const up = async () => {
			document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up);
			const duration = Number(card.dataset.previewDuration || originalDuration);
			const start = card.dataset.start;
			await this.persistTime(card.dataset.event, start, this.addMinutes(start, duration));
		};
		document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, { once: true });
	}

	showActionsMenu(event) {
		event.preventDefault(); event.stopPropagation();
		const button = event.currentTarget;
		const eventName = button.closest("[data-event]").dataset.event;
		if (this.actionsButton === button) {
			this.closeActionsMenu();
			return;
		}
		this.closeActionsMenu();
		this.actionsEventName = eventName;
		this.actionsButton = button;
		button.setAttribute("aria-expanded", "true");
		const rect = button.getBoundingClientRect();
		this.actionsMenu = $(`<div class="pc-event-actions-menu" role="menu">
			<button type="button" data-action="duplicate" role="menuitem">${frappe.utils.icon("copy", "sm")}<span>${__("Duplicar")}</span></button>
			<button type="button" data-action="unplan" role="menuitem">${frappe.utils.icon("calendar", "sm")}<span>${__("Desprogramar")}</span></button>
			<button type="button" data-action="delete" role="menuitem">${frappe.utils.icon("delete", "sm")}<span>${__("Eliminar")}</span></button>
		</div>`).appendTo(document.body);
		const width = this.actionsMenu.outerWidth();
		const height = this.actionsMenu.outerHeight();
		this.actionsMenu.css({
			left: `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width))}px`,
			top: `${Math.max(8, Math.min(window.innerHeight - height - 8, rect.bottom + 4))}px`,
		});
		this.actionsMenu.on("click", (menuEvent) => menuEvent.stopPropagation());
		this.actionsMenu.find('[data-action="duplicate"]').on("click", async () => {
			this.closeActionsMenu();
			await this.duplicateEvent(eventName);
		});
		this.actionsMenu.find('[data-action="unplan"]').on("click", async () => {
			this.closeActionsMenu();
			await this.unplanEvent(eventName);
		});
		this.actionsMenu.find('[data-action="delete"]').on("click", () => {
			this.closeActionsMenu();
			this.deleteEvent(eventName);
		});
		setTimeout(() => $(document).one("click.pc-event-actions", () => this.closeActionsMenu()), 0);
	}

	closeActionsMenu() {
		$(document).off("click.pc-event-actions");
		this.actionsMenu?.remove();
		this.actionsButton?.setAttribute("aria-expanded", "false");
		this.actionsMenu = null;
		this.actionsButton = null;
		this.actionsEventName = null;
	}

	editEvent(eventName) {
		const source = [...this.data.events, ...this.data.unplanned].find((row) => row.name === eventName);
		if (!source) return;
		const dialog = new frappe.ui.Dialog({
			title: __("Editar evento"),
			fields: [
				...this.eventFields(source),
				{ fieldtype: "Button", fieldname: "duplicate", label: __("Duplicar evento"), click: () => this.duplicateEvent(source.name, dialog) },
				{ fieldtype: "Button", fieldname: "unplan", label: __("Pasar a sin programar"), click: () => this.unplanEvent(source.name, dialog) },
				...(source.custom_stel_sync_status === "Conflict" ? [
					{ fieldtype: "Button", fieldname: "keep_erp", label: __("Resolver usando ERPNext"), click: () => this.resolveConflict(source.name, "erpnext", dialog) },
					{ fieldtype: "Button", fieldname: "keep_stel", label: __("Resolver usando STEL"), click: () => this.resolveConflict(source.name, "stel", dialog) },
				] : []),
			],
			primary_action_label: __("Guardar"),
			primary_action: async (values) => {
				delete values.duplicate;
				delete values.unplan;
				delete values.keep_erp;
				delete values.keep_stel;
				await frappe.call({
					method: "electrix_sync.api.planning.edit_planned_event",
					args: { event_name: source.name, ...this.eventPayload(values) },
					freeze: true,
					freeze_message: __("Actualizando ERPNext y STEL…"),
				});
				dialog.hide();
				await this.load();
			},
		});
		dialog.show();
	}

	createAt(day, minutes) {
		const startsOn = this.dateTime(day, minutes);
		const endsOn = this.addMinutes(startsOn, 60);
		const dialog = new frappe.ui.Dialog({
			title: __("Nuevo evento"),
			fields: this.eventFields({ starts_on: startsOn, ends_on: endsOn, status: "Open" }),
			primary_action_label: __("Crear y planificar"),
			primary_action: async (values) => {
				const payload = this.eventPayload(values);
				const employee = payload.employee;
				delete payload.employee;
				await frappe.call({
					method: "electrix_sync.api.planning.create_planned_event",
					args: { employee, ...payload },
					freeze: true,
					freeze_message: __("Creando evento en ERPNext y STEL…"),
				});
				dialog.hide();
				await this.load();
			},
		});
		dialog.show();
	}

	async dropUnplanned(event) {
		event.preventDefault();
		const dayColumn = event.currentTarget;
		dayColumn.classList.remove("is-over");
		const eventName = event.originalEvent.dataTransfer.getData("text/plain");
		const source = this.data.unplanned.find((row) => row.name === eventName);
		if (!source) return;
		const rect = dayColumn.getBoundingClientRect();
		const minutes = this.snapMinutes((event.originalEvent.clientY - rect.top) / 0.8);
		const employee = await this.selectCalendar();
		if (!employee) return;
		await frappe.call({
			method: "electrix_sync.api.planning.plan_event",
			args: { event_name: eventName, employee, starts_on: this.dateTime(dayColumn.dataset.day, minutes) },
			freeze: true,
			freeze_message: __("Planificando evento en ERPNext y STEL…"),
		});
		frappe.show_alert({ message: __("Evento planificado"), indicator: "green" });
		await this.load();
	}

	selectCalendar() {
		return new Promise((resolve) => {
			const dialog = new frappe.ui.Dialog({
				title: __("Asignar a calendario"),
				fields: [{ fieldtype: "Link", fieldname: "employee", label: __("Empleado / calendario"), options: "Employee", reqd: 1, get_query: () => ({ filters: { status: "Active", custom_stel_calendar_id: ["is", "set"] } }) }],
				primary_action_label: __("Asignar"),
				primary_action: (values) => { dialog.hide(); resolve(values.employee); },
			});
			dialog.$wrapper.one("hidden.bs.modal", () => resolve(null));
			dialog.show();
		});
	}

	eventFields(source) {
		const start = this.splitDateTime(source.starts_on);
		const end = this.splitDateTime(source.ends_on);
		const times = this.timeOptions();
		return [
			{ fieldtype: "Data", fieldname: "subject", label: __("Asunto"), reqd: 1, default: source.subject || "" },
			{ fieldtype: "Small Text", fieldname: "description", label: __("Descripción"), default: source.description || "" },
			{ fieldtype: "Select", fieldname: "account_type", label: __("Tipo de cuenta"), options: "\nCustomer\nLead", default: source.custom_account_type || source.reference_doctype || "" },
			{ fieldtype: "Dynamic Link", fieldname: "account", label: __("Cliente / potencial"), options: "account_type", default: source.custom_account || source.reference_docname || "" },
			{ fieldtype: "Link", fieldname: "location", label: __("Lugar"), options: "Lugar", default: source.custom_service_location || "", get_query: () => ({ filters: { status: "Activo" } }) },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Date", fieldname: "start_date", label: __("Fecha de inicio"), reqd: 1, default: start.date },
			{ fieldtype: "Select", fieldname: "start_time", label: __("Hora de inicio"), reqd: 1, options: times, default: start.time },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Date", fieldname: "end_date", label: __("Fecha de fin"), reqd: 1, default: end.date },
			{ fieldtype: "Select", fieldname: "end_time", label: __("Hora de fin"), reqd: 1, options: times, default: end.time },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Select", fieldname: "event_category", label: __("Categoría"), options: "Event\nMeeting\nCall\nSent/Received Email\nOther", default: source.event_category || "Event" },
			{ fieldtype: "Select", fieldname: "status", label: __("Estado"), options: "Open\nClosed\nCancelled", default: source.status || "Open" },
			{ fieldtype: "Link", fieldname: "employee", label: __("Empleado"), options: "Employee", reqd: 1, default: source.custom_assigned_employee || (source.assigned_employees || [])[0], get_query: () => ({ filters: { status: "Active" } }) },
		];
	}

	eventPayload(values) {
		const payload = { ...values };
		payload.starts_on = `${payload.start_date} ${payload.start_time}:00`;
		payload.ends_on = `${payload.end_date} ${payload.end_time}:00`;
		delete payload.start_date; delete payload.start_time; delete payload.end_date; delete payload.end_time;
		return payload;
	}

	splitDateTime(value) {
		const text = String(value || `${frappe.datetime.get_today()} 08:00:00`);
		const minute = Math.round(Number(text.slice(14, 16) || 0) / 15) * 15;
		const hour = Number(text.slice(11, 13) || 0) + Math.floor(minute / 60);
		return { date: text.slice(0, 10), time: `${String(hour % 24).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}` };
	}

	timeOptions() {
		return Array.from({ length: 96 }, (_, index) => `${String(Math.floor(index / 4)).padStart(2, "0")}:${String((index % 4) * 15).padStart(2, "0")}`).join("\n");
	}

	async duplicateEvent(eventName, dialog) {
		await frappe.call({ method: "electrix_sync.api.planning.duplicate_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Duplicando evento…") });
		dialog?.hide();
		frappe.show_alert({ message: __("Evento duplicado"), indicator: "green" });
		await this.load();
	}

	async unplanEvent(eventName, dialog) {
		await frappe.call({ method: "electrix_sync.api.planning.unplan_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Desprogramando evento…") });
		dialog?.hide();
		frappe.show_alert({ message: __("Evento desprogramado"), indicator: "green" });
		await this.load();
	}

	async resolveConflict(eventName, resolution, dialog) {
		await frappe.call({ method: "electrix_sync.api.outbound_sync.resolve_event_conflict", args: { event_name: eventName, resolution }, freeze: true, freeze_message: __("Resolviendo conflicto con STEL…") });
		dialog?.hide();
		frappe.show_alert({ message: __("Conflicto resuelto"), indicator: "green" });
		await this.load();
	}

	deleteEvent(eventName, dialog) {
		frappe.confirm(__("¿Eliminar esta cita de ERPNext y STEL Order?"), async () => {
			await frappe.call({ method: "electrix_sync.api.planning.delete_planned_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Eliminando evento…") });
			dialog?.hide();
			frappe.show_alert({ message: __("Evento eliminado"), indicator: "green" });
			await this.load();
		});
	}

	async persistTime(eventName, startsOn, endsOn) {
		try {
			await frappe.call({ method: "electrix_sync.api.planning.resize_event", args: { event_name: eventName, starts_on: startsOn, ends_on: endsOn }, freeze: true, freeze_message: __("Actualizando ERPNext y STEL…") });
			frappe.show_alert({ message: __("Evento actualizado"), indicator: "green" });
			await this.load();
		} catch (error) {
			frappe.show_alert({ message: __("No se pudo actualizar el evento"), indicator: "red" });
			await this.load();
		}
	}

	applyFilters() {
		this.page.main.find(".pc-event").each((_, card) => { card.style.display = this.visibleEmployees.has(card.dataset.employee) ? "" : "none"; });
	}

	snapMinutes(value) { return Math.max(0, Math.min(1425, Math.round(value / 15) * 15)); }
	snapDuration(value) { return Math.round(value / 15) * 15; }
	dateTime(day, minutes) {
		const dayOffset = Math.floor(minutes / 1440);
		const minuteOfDay = ((minutes % 1440) + 1440) % 1440;
		return `${frappe.datetime.add_days(day, dayOffset)} ${String(Math.floor(minuteOfDay / 60)).padStart(2, "0")}:${String(minuteOfDay % 60).padStart(2, "0")}:00`;
	}
	datetimeMinutes(value) { const date = new Date(String(value).replace(" ", "T")); return Math.round(date.getTime() / 60000); }
	addMinutes(value, minutes) { const date = new Date(String(value).replace(" ", "T")); date.setMinutes(date.getMinutes() + minutes); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}:00`; }
	minutes(value) { const time = (value || "").slice(11, 16).split(":").map(Number); return (time[0] || 0) * 60 + (time[1] || 0); }
	time(value) { return (value || "").slice(11, 16); }
	weekday(day) { return new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short" }).format(new Date(`${day}T12:00:00`)); }
}
