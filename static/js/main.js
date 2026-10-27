/* CampusMarks — small, dependency-free interactions. */
(function () {
    "use strict";

    /* ---------- Theme preference (presentation only, not application data) ---------- */
    var root = document.documentElement;
    var themeButtons = document.querySelectorAll("[data-theme-toggle]");

    function effectiveTheme() {
        return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    }

    function refreshThemeLabels() {
        var dark = effectiveTheme() === "dark";
        themeButtons.forEach(function (button) {
            var icon = button.querySelector("[data-theme-icon]");
            var label = button.querySelector("[data-theme-label]");
            if (icon) icon.textContent = dark ? "☀" : "◐";
            if (label) label.textContent = dark ? "Light mode" : "Dark mode";
            button.setAttribute(
                "aria-label",
                dark ? "Switch to light theme" : "Switch to dark theme"
            );
        });
    }

    themeButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            var next = effectiveTheme() === "dark" ? "light" : "dark";
            root.setAttribute("data-theme", next);
            try {
                localStorage.setItem("marks-theme", next);
            } catch (error) {
                /* The selected theme still works for this page. */
            }
            refreshThemeLabels();
        });
    });
    refreshThemeLabels();

    /* ---------- Mobile sidebar ---------- */
    var body = document.body;
    var openButton = document.querySelector("[data-sidebar-open]");
    var closeButtons = document.querySelectorAll("[data-sidebar-close]");
    var overlay = document.querySelector(".sidebar-overlay");

    function setSidebar(open) {
        body.classList.toggle("sidebar-open", open);
        if (overlay) {
            overlay.hidden = !open;
        }
        if (openButton) {
            openButton.setAttribute("aria-expanded", open ? "true" : "false");
        }
    }

    if (openButton) {
        openButton.addEventListener("click", function () {
            setSidebar(true);
        });
    }

    closeButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            setSidebar(false);
        });
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            setSidebar(false);
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 1050) {
            setSidebar(false);
        }
    });

    /* ---------- Flash messages ---------- */
    document.querySelectorAll("[data-dismiss-flash]").forEach(function (button) {
        button.addEventListener("click", function () {
            var flash = button.closest(".flash");
            if (flash) flash.remove();
        });
    });

    /* ---------- Destructive confirmations ---------- */
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            var message = form.getAttribute("data-confirm") || "Are you sure?";
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    /* ---------- Print buttons ---------- */
    document.querySelectorAll("[data-print]").forEach(function (button) {
        button.addEventListener("click", function () {
            window.print();
        });
    });

    /* ---------- Marks entry client-side hints ----------
       Python validation remains the source of truth. This only prevents an
       obviously invalid save and helps the user see which field is wrong. */
    document.querySelectorAll("[data-marks-form]").forEach(function (form) {
        var errorBox = form.querySelector("[data-client-error]");
        var inputs = form.querySelectorAll(".mark-input");

        function showError(message) {
            if (!errorBox) return;
            errorBox.textContent = message;
            errorBox.hidden = false;
        }

        function clearError() {
            if (!errorBox) return;
            errorBox.textContent = "";
            errorBox.hidden = true;
        }

        form.addEventListener("submit", function (event) {
            clearError();
            var invalidMessage = "";
            inputs.forEach(function (input) {
                var raw = input.value.trim();
                if (raw === "") return;
                var value = Number(raw);
                var maximum = Number(input.getAttribute("data-max"));
                var name = input.getAttribute("data-subject-name") || "Subject";
                if (!Number.isFinite(value)) {
                    invalidMessage = name + ": enter a valid number.";
                } else if (value < 0) {
                    invalidMessage = name + ": marks cannot be negative.";
                } else if (value > maximum) {
                    invalidMessage =
                        name + ": marks cannot exceed the maximum of " + maximum + ".";
                }
                if (invalidMessage) {
                    input.focus();
                }
            });
            if (invalidMessage) {
                event.preventDefault();
                showError(invalidMessage);
            }
        });

        inputs.forEach(function (input) {
            input.addEventListener("input", clearError);
        });
    });
}());
