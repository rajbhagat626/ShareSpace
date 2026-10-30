// ShareSpace Client Interactions

document.addEventListener('DOMContentLoaded', () => {
    // 1. Auto-dismiss flash alerts after 5 seconds
    const flashes = document.querySelectorAll('.flash-msg');
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.opacity = '0';
            flash.style.transition = 'opacity 0.4s ease';
            setTimeout(() => flash.remove(), 400);
        }, 5000);
    });

    // 2. Return Modal Handling
    const returnModal = document.getElementById('returnModal');
    const returnButtons = document.querySelectorAll('.btn-return-modal');
    const returnBookingIdInput = document.getElementById('modalBookingId');
    const returnResourceTitleSpan = document.getElementById('modalResourceTitle');
    const returnConditionSelect = document.getElementById('returnCondition');
    const damageNotice = document.getElementById('damageNotice');

    if (returnButtons.length > 0 && returnModal) {
        returnButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const bookingId = btn.getAttribute('data-booking-id');
                const resourceTitle = btn.getAttribute('data-resource-title');
                
                returnBookingIdInput.value = bookingId;
                if (returnResourceTitleSpan) {
                    returnResourceTitleSpan.textContent = resourceTitle;
                }
                document.getElementById('returnForm').action = `/booking/${bookingId}/return`;
                returnModal.classList.add('active');
            });
        });

        // Close Return Modal
        const closeBtn = returnModal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                returnModal.classList.remove('active');
            });
        }
    }

    // Toggle damage warning inside return modal
    if (returnConditionSelect && damageNotice) {
        returnConditionSelect.addEventListener('change', (e) => {
            if (e.target.value === 'Damaged') {
                damageNotice.style.display = 'block';
            } else {
                damageNotice.style.display = 'none';
            }
        });
    }

    // 3. Quick Incident Modal Handling
    const incidentModal = document.getElementById('incidentModal');
    const openIncidentBtns = document.querySelectorAll('.btn-report-incident');
    if (openIncidentBtns.length > 0 && incidentModal) {
        openIncidentBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const resourceId = btn.getAttribute('data-resource-id');
                const resourceInput = document.getElementById('incidentResourceId');
                if (resourceInput) resourceInput.value = resourceId;
                incidentModal.classList.add('active');
            });
        });

        const closeIncidentBtn = incidentModal.querySelector('.modal-close');
        if (closeIncidentBtn) {
            closeIncidentBtn.addEventListener('click', () => {
                incidentModal.classList.remove('active');
            });
        }
    }

    // Close any modal when clicking overlay outside box
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal-overlay')) {
            e.target.classList.remove('active');
        }
    });

    // 4. Date validation for Booking Request
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    if (startDateInput && endDateInput) {
        // Default start date to today if empty
        const todayStr = new Date().toISOString().split('T')[0];
        if (!startDateInput.value) startDateInput.value = todayStr;
        startDateInput.min = todayStr;

        startDateInput.addEventListener('change', () => {
            endDateInput.min = startDateInput.value;
            if (endDateInput.value && endDateInput.value < startDateInput.value) {
                endDateInput.value = startDateInput.value;
            }
        });
    }
});
