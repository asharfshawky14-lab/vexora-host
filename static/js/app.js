
"use strict";

(() => {
    const body = document.body;
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebarBackdrop");

    if (!body) {
        return;
    }

    const mobileQuery = window.matchMedia("(max-width: 760px)");

    function setMenuOpen(open) {
        const shouldOpen = Boolean(open) && mobileQuery.matches;

        body.classList.toggle("sidebar-open", shouldOpen);

        if (menuToggle) {
            menuToggle.setAttribute(
                "aria-expanded",
                shouldOpen ? "true" : "false"
            );

            menuToggle.setAttribute(
                "aria-label",
                shouldOpen ? "إغلاق القائمة" : "فتح القائمة"
            );
        }

        if (sidebar) {
            sidebar.setAttribute(
                "aria-hidden",
                mobileQuery.matches && !shouldOpen ? "true" : "false"
            );
        }

        if (backdrop) {
            backdrop.setAttribute(
                "aria-hidden",
                shouldOpen ? "false" : "true"
            );
        }

        if (shouldOpen && menuToggle) {
            const focusable = sidebar?.querySelector(
                'a[href], button:not(:disabled), input:not(:disabled), ' +
                'select:not(:disabled), textarea:not(:disabled), ' +
                '[tabindex]:not([tabindex="-1"])'
            );

            if (focusable) {
                focusable.focus({ preventScroll: true });
            }
        }
    }

    if (menuToggle) {
        menuToggle.addEventListener("click", () => {
            const isOpen = body.classList.contains("sidebar-open");
            setMenuOpen(!isOpen);
        });
    }

    if (backdrop) {
        backdrop.addEventListener("click", () => {
            setMenuOpen(false);
        });
    }

    if (sidebar) {
        sidebar.addEventListener("click", (event) => {
            const link = event.target.closest("a[href]");

            if (link && mobileQuery.matches) {
                setMenuOpen(false);
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            setMenuOpen(false);
        }

        // Keep keyboard focus inside the open mobile navigation.
        if (
            event.key === "Tab" &&
            mobileQuery.matches &&
            body.classList.contains("sidebar-open") &&
            sidebar
        ) {
            const focusable = Array.from(
                sidebar.querySelectorAll(
                    'a[href], button:not(:disabled), input:not(:disabled), ' +
                    'select:not(:disabled), textarea:not(:disabled), ' +
                    '[tabindex]:not([tabindex="-1"])'
                )
            ).filter((element) => {
                return element.getClientRects().length > 0;
            });

            if (focusable.length === 0) {
                event.preventDefault();
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];

            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (
                !event.shiftKey &&
                document.activeElement === last
            ) {
                event.preventDefault();
                first.focus();
            }
        }
    });

    function handleViewportChange() {
        setMenuOpen(false);

        if (sidebar) {
            sidebar.setAttribute(
                "aria-hidden",
                mobileQuery.matches ? "true" : "false"
            );
        }
    }

    if (typeof mobileQuery.addEventListener === "function") {
        mobileQuery.addEventListener("change", handleViewportChange);
    } else {
        // Compatibility with older mobile browsers.
        mobileQuery.addListener(handleViewportChange);
    }

    // Dismissible flash messages.
    document.querySelectorAll(".flash-close").forEach((button) => {
        button.addEventListener("click", () => {
            const message = button.closest(".flash-message");

            if (message) {
                message.remove();
            }
        });
    });

    // Confirm destructive actions only when explicitly marked.
    document.querySelectorAll("[data-confirm]").forEach((element) => {
        element.addEventListener("click", (event) => {
            const message =
                element.getAttribute("data-confirm") ||
                "هل أنت متأكد من تنفيذ العملية دي؟";

            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    // Prevent accidental duplicate submissions on forms explicitly marked.
    document.querySelectorAll("form[data-prevent-double-submit]").forEach(
        (form) => {
            form.addEventListener("submit", (event) => {
                if (form.dataset.submitting === "true") {
                    event.preventDefault();
                    return;
                }

                if (!form.checkValidity()) {
                    return;
                }

                form.dataset.submitting = "true";

                const submitButton = form.querySelector(
                    'button[type="submit"], input[type="submit"]'
                );

                if (submitButton) {
                    submitButton.disabled = true;
                    submitButton.setAttribute("aria-busy", "true");
                }
            });
        }
    );

    // Initial state.
    handleViewportChange();
})();
