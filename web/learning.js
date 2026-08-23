(() => {
    "use strict";

    const content = document.getElementById("learning-content");
    const timezoneLabel = document.getElementById("timezone-label");
    const periodButtons = [...document.querySelectorAll("[data-period]")];
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    let selectedPeriod = "day";
    let aggregates = null;

    function resolvedWeekStart() {
        if (timezone === "Asia/Jerusalem") return 6;
        try {
            const locale = new Intl.Locale(navigator.language);
            const info = locale.getWeekInfo ? locale.getWeekInfo() : locale.weekInfo;
            if (info && Number.isInteger(info.firstDay)) {
                return info.firstDay - 1;
            }
        } catch (_) {
            // Older browsers use the conservative Monday-first fallback.
        }
        return 0;
    }

    function localDateLabel(isoDate) {
        const date = new Date(`${isoDate}T12:00:00`);
        return new Intl.DateTimeFormat(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
        }).format(date);
    }

    function metric(label, value) {
        const wrapper = document.createElement("div");
        wrapper.className = "metric";
        const term = document.createElement("dt");
        term.textContent = label;
        const number = document.createElement("dd");
        number.textContent = String(value);
        wrapper.append(term, number);
        return wrapper;
    }

    function render() {
        if (!aggregates) return;
        const period = aggregates.periods[selectedPeriod];
        content.replaceChildren();
        content.setAttribute("aria-busy", "false");

        const metrics = document.createElement("dl");
        metrics.className = "metrics";
        metrics.append(
            metric("Total changes", period.total_changes),
            metric("Skills created or updated", period.skills_created_updated),
            metric("Rules changed", period.rules_changed),
            metric("Dreams consolidated", period.dreams_consolidated),
        );

        const summarySection = document.createElement("section");
        summarySection.className = "summary-section";
        const heading = document.createElement("div");
        heading.className = "summary-heading";
        const title = document.createElement("h2");
        title.textContent = "In short";
        const windowStart = document.createElement("p");
        windowStart.className = "window-start";
        windowStart.textContent = `Since ${localDateLabel(period.window_start.slice(0, 10))}`;
        heading.append(title, windowStart);

        const list = document.createElement("ul");
        list.className = "daily-list";
        if (period.daily_summaries.length === 0) {
            const empty = document.createElement("li");
            empty.className = "empty-summary";
            empty.textContent = "No learning changes in this period.";
            list.append(empty);
        } else {
            for (const item of period.daily_summaries) {
                const row = document.createElement("li");
                const date = document.createElement("time");
                date.dateTime = item.date;
                date.textContent = localDateLabel(item.date);
                const summary = document.createElement("p");
                summary.textContent = item.summary;
                row.append(date, summary);
                list.append(row);
            }
        }

        summarySection.append(heading, list);
        content.append(metrics, summarySection);
    }

    async function load() {
        timezoneLabel.textContent = timezone.replaceAll("_", " ");
        const params = new URLSearchParams({
            timezone,
            week_start: String(resolvedWeekStart()),
        });
        try {
            const response = await fetch(`/api/learning?${params}`, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`Learning request failed (${response.status})`);
            aggregates = await response.json();
            render();
        } catch (error) {
            content.setAttribute("aria-busy", "false");
            const message = document.createElement("p");
            message.className = "error-message";
            message.textContent = "Learning is unavailable right now.";
            content.replaceChildren(message);
            console.error(error);
        }
    }

    for (const button of periodButtons) {
        button.addEventListener("click", () => {
            selectedPeriod = button.dataset.period;
            for (const candidate of periodButtons) {
                candidate.setAttribute(
                    "aria-pressed",
                    String(candidate === button),
                );
            }
            render();
        });
    }

    load();
})();
