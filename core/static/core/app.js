document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-loading-form]").forEach((form) => {
        form.addEventListener("submit", () => {
            const button = form.querySelector("button[type='submit']");
            const label = button?.querySelector("[data-button-label]");
            const status = form.querySelector("[data-loading-status]");

            if (button) button.disabled = true;
            if (label) label.textContent = "Searching...";
            if (status) status.hidden = false;
        });
    });
});
