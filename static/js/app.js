
"use strict";

document.addEventListener("DOMContentLoaded", function () {
    const menuToggle = document.getElementById("menuToggle");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const sidebar = document.getElementById("sidebar");

    function closeSidebar() {
        document.body.classList.remove("sidebar-open");

        if (menuToggle) {
            menuToggle.setAttribute("aria-expanded", "false");
        }
    }

    function toggleSidebar() {
        const isOpen = document.body.classList.toggle("sidebar-open");

        if (menuToggle) {
            menuToggle.setAttribute("aria-expanded", String(isOpen));
        }
    }

    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", toggleSidebar);
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener("click", closeSidebar);
    }

    if (sidebar) {
        sidebar.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                closeSidebar();
            });
        });
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeSidebar();
        }
    });

    window.addEventListener("resize", function () {
        if (window.innerWidth > 760) {
            closeSidebar();
        }
    });

    document.querySelectorAll("[data-confirm]").forEach(function (element) {
        element.addEventListener("click", function (event) {
            const message =
                element.getAttribute("data-confirm") ||
                "Are you sure you want to continue?";

            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("[data-copy-target]").forEach(function (button) {
        button.addEventListener("click", async function () {
            const selector = button.getAttribute("data-copy-target");
            const target = selector ? document.querySelector(selector) : null;

            if (!target) {
                return;
            }

            const value =
                "value" in target ? target.value : target.textContent;

            try {
                await navigator.clipboard.writeText(value || "");

                const originalText = button.textContent;
                button.textContent = "Copied!";

                window.setTimeout(function () {
                    button.textContent = originalText;
                }, 1500);
            } catch (error) {
                window.prompt("Copy the text below:", value || "");
            }
        });
    });

    document.querySelectorAll("form[data-confirm-submit]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            const message =
                form.getAttribute("data-confirm-submit") ||
                "Are you sure you want to submit this form?";

            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
});
