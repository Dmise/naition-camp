document.addEventListener('DOMContentLoaded', () => {
    const registrationSection = document.getElementById('registration');
    const registrationPanel = document.querySelector('.registration-panel');
    const form = document.getElementById('registration-form');
    const message = document.getElementById('form-message');
    const planInput = document.getElementById('plan-input');
    const planLabel = document.getElementById('form-plan-label');
    const stickyCta = document.querySelector('.sticky-cta');
    const hero = document.querySelector('.hero');

    let formFocusTracked = false;

    function trackGoal(name, params) {
        if (typeof ym === 'function') {
            ym(111696929, 'reachGoal', name, params);
        }
    }

    function scrollToRegistration(source, plan) {
        if (!registrationSection) {
            return;
        }

        if (plan && planInput) {
            planInput.value = plan;
        }

        if (planLabel && plan) {
            planLabel.textContent = 'Тариф: ' + plan + ' — мы свяжемся для подтверждения';
            planLabel.hidden = false;
        }

        registrationSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        window.setTimeout(() => {
            if (registrationPanel) {
                registrationPanel.classList.add('registration-panel--highlight');
                window.setTimeout(() => {
                    registrationPanel.classList.remove('registration-panel--highlight');
                }, 2500);
            }

            const nameInput = form?.querySelector('input[name="name"]');
            if (nameInput instanceof HTMLInputElement) {
                nameInput.focus({ preventScroll: true });
            }
        }, 400);

        trackGoal('cta_click', { source: source || 'unknown', plan: plan || '' });
    }

    document.querySelectorAll('[data-scroll-registration]').forEach((element) => {
        element.addEventListener('click', (event) => {
            event.preventDefault();
            const source = element.getAttribute('data-scroll-registration') || 'link';
            scrollToRegistration(source);
        });
    });

    document.querySelectorAll('.btn-register').forEach((button) => {
        button.addEventListener('click', () => {
            const card = button.closest('.pricing-card');
            const planName = card?.querySelector('h3')?.textContent?.trim() || '';
            scrollToRegistration('pricing', planName);
        });
    });

    if (hero && stickyCta) {
        const observer = new IntersectionObserver(
            ([entry]) => {
                stickyCta.hidden = entry.isIntersecting;
                document.body.classList.toggle('has-sticky-cta', !entry.isIntersecting);
            },
            { threshold: 0.1 }
        );
        observer.observe(hero);
    }

    document.querySelectorAll('.program-module').forEach((module, index) => {
        const toggle = module.querySelector('.program-module-toggle');
        const body = module.querySelector('.program-module-body');

        if (!(toggle instanceof HTMLButtonElement) || !body) {
            return;
        }

        const setOpen = (open) => {
            module.classList.toggle('is-open', open);
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            body.hidden = !open;
        };

        setOpen(index === 0);

        toggle.addEventListener('click', () => {
            const willOpen = !module.classList.contains('is-open');
            setOpen(willOpen);
            if (willOpen) {
                trackGoal('program_expand', { module: toggle.textContent?.trim() || '' });
            }
        });
    });

    if (form) {
        form.addEventListener('focusin', () => {
            if (!formFocusTracked) {
                formFocusTracked = true;
                trackGoal('form_focus');
            }
        });

        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            const submitButton = form.querySelector('button[type="submit"]');
            const formData = new FormData(form);

            if (submitButton instanceof HTMLButtonElement) {
                submitButton.disabled = true;
            }

            if (message) {
                message.textContent = '';
                message.className = 'form-message';
            }

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    body: formData,
                });

                const data = await response.json();

                if (!response.ok || !data.ok) {
                    throw new Error(data.error || 'Не удалось отправить заявку.');
                }

                trackGoal('form_submit');

                if (message) {
                    message.textContent = 'Заявка успешно отправлена. Мы свяжемся с вами в ближайшее время.';
                    message.className = 'form-message success';
                }

                form.reset();
                if (planLabel) {
                    planLabel.hidden = true;
                }
                if (planInput) {
                    planInput.value = '';
                }

                loadOrderStats();
            } catch (error) {
                if (message) {
                    message.textContent = error instanceof Error ? error.message : 'Не удалось отправить заявку.';
                    message.className = 'form-message error';
                }
            } finally {
                if (submitButton instanceof HTMLButtonElement) {
                    submitButton.disabled = false;
                }
            }
        });
    }

    async function loadOrderStats() {
        const countEl = document.getElementById('orders-count');
        const spotsEl = document.getElementById('spots-left');

        if (!countEl && !spotsEl) {
            return;
        }

        try {
            const response = await fetch('api/stats.php');
            const data = await response.json();

            if (!data.ok) {
                return;
            }

            if (countEl) {
                countEl.textContent = String(data.orders_count);
            }

            if (spotsEl) {
                spotsEl.textContent = String(data.spots_left);
            }
        } catch {
            // keep static fallback text
        }
    }

    loadOrderStats();
});
