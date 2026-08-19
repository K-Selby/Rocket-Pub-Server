console.log("Pub Booking System loaded.");


function normalisePhone(phone) {
    let cleaned = (phone || "").replace(/\D/g, "");

    if (cleaned.startsWith("44") && cleaned.length >= 12) {
        cleaned = "0" + cleaned.slice(2);
    }

    return cleaned;
}


function calculateDeposit(partySize) {
    const size = Number(partySize || 0);
    return size > 10 ? Math.min(size * 5, 100) : 0;
}


function setupCustomerLookup() {
    const customers = window.PUB_CUSTOMERS || [];
    const nameInput = document.getElementById("customer-name");
    const phoneInput = document.getElementById("customer-phone");

    if (!nameInput || !phoneInput) return;

    const areaSelect = document.getElementById("preferred-area");
    const tableSelect = document.getElementById("preferred-table");
    const nearTv = document.getElementById("wants-near-tv");
    const avoidsBench = document.getElementById("avoids-bench");
    const message = document.getElementById("returning-customer-message");

    function applyCustomer(customer) {
        if (!customer) return;

        nameInput.value = customer.name;
        phoneInput.value = customer.phone;
        areaSelect.value = customer.preferred_area_id || "";
        tableSelect.value = customer.preferred_table_id || "";
        nearTv.checked = Boolean(customer.prefers_near_tv);
        avoidsBench.checked = Boolean(customer.avoids_bench);
        message.hidden = false;
    }

    phoneInput.addEventListener("input", () => {
        const phone = normalisePhone(phoneInput.value);
        const customer = customers.find(
            item => normalisePhone(item.phone) === phone && phone.length > 0
        );

        if (customer) {
            applyCustomer(customer);
        } else {
            message.hidden = true;
        }
    });

    nameInput.addEventListener("change", () => {
        const name = nameInput.value.trim().toLowerCase();
        const matches = customers.filter(
            item => item.name.trim().toLowerCase() === name
        );

        if (matches.length === 1) applyCustomer(matches[0]);
    });
}


function setupBookingTimeValidation() {
    const form = document.getElementById("booking-form");
    const dateInput = document.getElementById("booking-date");
    const timeInput = document.getElementById("booking-time");

    if (!form || !dateInput || !timeInput) return;

    const today = form.dataset.today;
    const nowTime = form.dataset.now;
    const editing = form.dataset.editing === "1";
    const originalDate = dateInput.value;
    const originalTime = timeInput.value;

    function latestTime() {
        if (!dateInput.value) return "19:30";

        const selected = new Date(dateInput.value + "T12:00:00");
        return selected.getDay() === 0 ? "19:00" : "19:30";
    }

    function invalidMessage() {
        const latest = latestTime();
        const latestDisplay = latest === "19:00" ? "7:00pm" : "7:30pm";

        if (dateInput.value < today) {
            return "Bookings cannot be created for a previous day.";
        }

        if (
            dateInput.value === today &&
            timeInput.value &&
            timeInput.value <= nowTime
        ) {
            return "That time has already passed. Please choose a later time.";
        }

        return (
            "The earliest available booking time is 12:15pm and " +
            `the latest available time is ${latestDisplay}.`
        );
    }

    function validate(showPopup = true) {
        if (!timeInput.value || !dateInput.value) return true;

        // Existing historical bookings can still be opened/edited without
        // instantly blanking their original slot. Moving them to another past
        // slot is still rejected by the server.
        const unchangedHistoricalEdit = (
            editing &&
            dateInput.value === originalDate &&
            timeInput.value === originalTime
        );

        if (unchangedHistoricalEdit) return true;

        const invalidDate = dateInput.value < today;
        const invalidHours = (
            timeInput.value < "12:15" ||
            timeInput.value > latestTime()
        );
        const pastToday = (
            dateInput.value === today &&
            timeInput.value <= nowTime
        );

        if (invalidDate || invalidHours || pastToday) {
            timeInput.value = "";

            if (showPopup) alert(invalidMessage());
            return false;
        }

        return true;
    }

    timeInput.addEventListener("change", () => validate(true));
    dateInput.addEventListener("change", () => validate(true));
}


function setupKitchenWarning() {
    const dateInput = document.getElementById("booking-date");
    const timeInput = document.getElementById("booking-time");
    const warning = document.getElementById("late-food-warning");
    const eating = document.getElementById("is-eating-food");

    if (!dateInput || !timeInput || !warning) return;

    function update() {
        if (
            !dateInput.value ||
            !timeInput.value ||
            timeInput.value <= "18:45" ||
            (eating && !eating.checked)
        ) {
            warning.hidden = true;
            return;
        }

        const selectedDate = new Date(dateInput.value + "T12:00:00");
        const closeTime = selectedDate.getDay() === 0 ? "7:30pm" : "8:00pm";

        warning.textContent =
            `Please let the customer know that the kitchen closes at ${closeTime}. ` +
            "Depending on how busy we are, they may need to order promptly " +
            "to make sure we are able to accept their food order.";

        warning.hidden = false;
    }

    dateInput.addEventListener("change", update);
    timeInput.addEventListener("change", update);
    if (eating) eating.addEventListener("change", update);
    update();
}


function setupDepositWarning() {
    const partyInput = document.getElementById("party-size");
    const warning = document.getElementById("deposit-warning");
    const paymentField = document.getElementById("deposit-payment-field");
    const paidInput = document.getElementById("deposit-paid-amount");

    if (!partyInput || !warning || !paymentField || !paidInput) return;

    function update() {
        const due = calculateDeposit(partyInput.value);

        if (due <= 0) {
            warning.hidden = true;
            paymentField.hidden = true;
            return;
        }

        warning.textContent =
            `A deposit of £${due.toFixed(2)} may be required. ` +
            "Please let the customer know that we will call them back to confirm the deposit.";

        warning.hidden = false;
        paymentField.hidden = false;
        paidInput.max = due.toFixed(2);

        const remainder = document.getElementById("deposit-remainder-preview");
        if (remainder) {
            const paid = Number(paidInput.value || 0);
            remainder.textContent = `£${Math.max(due - paid, 0).toFixed(2)}`;
        }
    }

    partyInput.addEventListener("input", update);
    paidInput.addEventListener("input", update);
    update();
}


function setupLargePartyDepositWarning() {
    const partyInput = document.getElementById("large-party-size");
    const warning = document.getElementById("large-deposit-warning");
    const paymentField = document.getElementById("large-deposit-payment-field");
    const paidInput = document.getElementById("large-deposit-paid");

    if (!partyInput || !warning || !paymentField || !paidInput) return;

    function update() {
        const due = calculateDeposit(partyInput.value);

        if (due <= 0) {
            warning.hidden = true;
            paymentField.hidden = true;
            return;
        }

        warning.textContent =
            `If this enquiry proceeds, a deposit of £${due.toFixed(2)} may be required.`;

        warning.hidden = false;
        paymentField.hidden = false;
        paidInput.max = due.toFixed(2);
    }

    partyInput.addEventListener("input", update);
    update();
}


function setupLargePartyFoodQuote() {
    const partyInput = document.getElementById("large-party-size");
    const cateredInput = document.getElementById("catered-people");
    const optionSelect = document.getElementById("menu-option");
    const preview = document.getElementById("food-quote-preview");

    if (!partyInput || !cateredInput || !optionSelect || !preview) return;

    function update() {
        const partySize = Number(partyInput.value || 0);
        let catered = Number(cateredInput.value || 0);

        if (partySize > 0 && catered > partySize) {
            catered = partySize;
            cateredInput.value = partySize;
        }

        const selected = optionSelect.options[optionSelect.selectedIndex];
        const price = selected && selected.dataset.price
            ? Number(selected.dataset.price)
            : null;

        preview.textContent = (
            catered > 0 && price !== null
                ? `£${(price * catered).toFixed(2)}`
                : "Not calculated"
        );

        document.dispatchEvent(new CustomEvent("largePartyQuoteChanged"));
    }

    partyInput.addEventListener("input", update);
    cateredInput.addEventListener("input", update);
    optionSelect.addEventListener("change", update);
    update();
}


function setupExtraDishes() {
    const container = document.getElementById("extra-dish-rows");
    const addButton = document.getElementById("add-extra-dish");
    const template = document.getElementById("extra-dish-template");
    const totalPreview = document.getElementById("extras-total-preview");

    if (!container || !addButton || !template || !totalPreview) return;

    function updateTotal() {
        let total = 0;

        container.querySelectorAll(".extra-dish-row").forEach(row => {
            const price = Number(
                row.querySelector(".extra-dish-price").value || 0
            );
            const quantity = Number(
                row.querySelector(".extra-dish-quantity").value || 0
            );

            total += price * quantity;
        });

        totalPreview.textContent = `£${total.toFixed(2)}`;

        const mainPreview = document.getElementById("food-quote-preview");
        const grandPreview = document.getElementById("large-grand-total-preview");
        const remainderPreview = document.getElementById("large-total-remainder-preview");
        const depositPaidInput = document.getElementById("large-deposit-paid");

        const mainTotal = mainPreview && mainPreview.textContent.startsWith("£")
            ? Number(mainPreview.textContent.replace("£", ""))
            : 0;

        const grandTotal = mainTotal + total;

        if (grandPreview) {
            grandPreview.textContent = `£${grandTotal.toFixed(2)}`;
        }

        if (remainderPreview) {
            const paid = Number(depositPaidInput?.value || 0);
            remainderPreview.textContent =
                `£${Math.max(grandTotal - paid, 0).toFixed(2)}`;
        }
    }

    function configureRow(row) {
        const select = row.querySelector(".extra-dish-select");
        const customField = row.querySelector(".custom-dish-field");
        const customName = row.querySelector(".custom-dish-name");
        const hiddenName = row.querySelector(".extra-dish-name");
        const hiddenCustom = row.querySelector(".extra-dish-custom");
        const price = row.querySelector(".extra-dish-price");
        const quantity = row.querySelector(".extra-dish-quantity");
        const remove = row.querySelector(".remove-extra");

        function syncDish() {
            if (select.value === "__custom__") {
                customField.hidden = false;
                hiddenCustom.value = "1";
                hiddenName.value = customName.value.trim();
            } else {
                customField.hidden = true;
                hiddenCustom.value = "0";
                hiddenName.value = select.value;

                const option = select.options[select.selectedIndex];

                if (option && option.dataset.price) {
                    price.value = Number(option.dataset.price).toFixed(2);
                }
            }

            updateTotal();
        }

        select.addEventListener("change", syncDish);

        customName.addEventListener("input", () => {
            hiddenName.value = customName.value.trim();
        });

        price.addEventListener("input", updateTotal);
        quantity.addEventListener("input", updateTotal);

        remove.addEventListener("click", () => {
            row.remove();
            updateTotal();
        });

        syncDish();
    }

    container.querySelectorAll(".extra-dish-row").forEach(configureRow);

    addButton.addEventListener("click", () => {
        const row = template.content.firstElementChild.cloneNode(true);
        container.appendChild(row);
        configureRow(row);
    });

    document.addEventListener("largePartyQuoteChanged", updateTotal);

    const depositPaidInput = document.getElementById("large-deposit-paid");
    if (depositPaidInput) {
        depositPaidInput.addEventListener("input", updateTotal);
    }

    updateTotal();
}



function setupLargePartyEndTime() {
    const restOfDay = document.getElementById("reserve-for-rest-of-day");
    const endField = document.getElementById("expected-end-time-field");
    const endInput = document.getElementById("expected-end-time");

    if (!restOfDay || !endField || !endInput) return;

    function update() {
        if (restOfDay.checked) {
            endField.hidden = true;
            endInput.value = "";
            endInput.required = false;
        } else {
            endField.hidden = false;
            endInput.required = true;
        }
    }

    restOfDay.addEventListener("change", update);
    update();
}



function setupLargePartyAreaFiltering() {
    const areaCheckboxes = Array.from(
        document.querySelectorAll(".reserved-area-checkbox")
    );
    const tableCards = Array.from(
        document.querySelectorAll(".large-reserve-table")
    );

    if (!areaCheckboxes.length || !tableCards.length) return;

    function update() {
        const selectedAreas = new Set(
            areaCheckboxes
                .filter(box => box.checked)
                .map(box => box.value)
        );

        tableCards.forEach(card => {
            if (selectedAreas.size === 0) {
                card.hidden = false;
                return;
            }

            card.hidden = !selectedAreas.has(card.dataset.areaId);

            // If a table becomes hidden because its area isn't selected,
            // clear its individual selection to avoid invisible reservations.
            if (card.hidden) {
                const checkbox = card.querySelector('input[type="checkbox"]');
                if (checkbox) checkbox.checked = false;
            }
        });
    }

    areaCheckboxes.forEach(box => box.addEventListener("change", update));
    update();
}


function setupInquiryReminders() {
    const container = document.getElementById("reminder-rows");
    const template = document.getElementById("reminder-template");
    const addButton = document.getElementById("add-reminder");

    if (!container || !template || !addButton) return;

    function configure(row) {
        const remove = row.querySelector(".remove-reminder");

        if (remove) {
            remove.addEventListener("click", () => row.remove());
        }
    }

    container.querySelectorAll(".reminder-row").forEach(configure);

    addButton.addEventListener("click", () => {
        const row = template.content.firstElementChild.cloneNode(true);
        container.appendChild(row);
        configure(row);
    });
}


function setupNormalTableAvailability() {
    const form = document.getElementById("booking-form");
    const dateInput = document.getElementById("booking-date");
    const timeInput = document.getElementById("booking-time");
    const partyInput = document.getElementById("party-size");
    const areaInput = document.getElementById("preferred-area");
    const nearTv = document.getElementById("wants-near-tv");
    const avoidsBench = document.getElementById("avoids-bench");
    const eating = document.getElementById("is-eating-food");
    const tableCards = Array.from(
        document.querySelectorAll(".availability-table")
    );
    const pairingList = document.getElementById("pairing-suggestion-list");

    if (
        !form || !dateInput || !timeInput || !partyInput ||
        !tableCards.length || !pairingList
    ) {
        return;
    }

    async function update() {
        if (!dateInput.value || !timeInput.value || !partyInput.value) {
            tableCards.forEach(card => {
                card.classList.remove(
                    "table-ideal",
                    "table-suitable",
                    "table-unavailable",
                    "table-too-small"
                );
            });
            pairingList.innerHTML = "";
            return;
        }

        const params = new URLSearchParams({
            date: dateInput.value,
            time: timeInput.value,
            party_size: partyInput.value,
            preferred_area_id: areaInput?.value || "",
            wants_near_tv: nearTv?.checked ? "1" : "0",
            avoids_bench: avoidsBench?.checked ? "1" : "0",
            is_eating_food: eating?.checked ? "1" : "0",
            exclude_booking_id: form.dataset.bookingId || "",
        });

        const response = await fetch(`/api/table-availability?${params}`);
        const data = await response.json();

        const byId = new Map(
            data.tables.map(table => [String(table.id), table])
        );

        tableCards.forEach(card => {
            const table = byId.get(card.dataset.tableId);
            const checkbox = card.querySelector('input[type="checkbox"]');

            card.classList.remove(
                "table-ideal",
                "table-suitable",
                "table-unavailable",
                "table-too-small"
            );

            if (!table) return;

            if (table.status === "unavailable") {
                card.classList.add("table-unavailable");
                checkbox.disabled = true;
                checkbox.checked = false;
            } else if (table.status === "ideal") {
                card.classList.add("table-ideal");
                checkbox.disabled = false;
            } else if (table.status === "suitable") {
                card.classList.add("table-suitable");
                checkbox.disabled = false;
            } else if (table.status === "too_small") {
                card.classList.add("table-too-small");
                // Too-small tables can still be chosen as part of a configured
                // multi-table combination, so don't disable them.
                checkbox.disabled = false;
            } else {
                checkbox.disabled = false;
            }
        });

        pairingList.innerHTML = "";

        data.groups.forEach(group => {
            if (group.table_ids.length <= 1) return;

            const button = document.createElement("button");
            button.type = "button";
            button.className = "pairing-option";
            button.textContent =
                `T${group.numbers.join(" + T")} · ${group.capacity} seats`;

            button.addEventListener("click", () => {
                tableCards.forEach(card => {
                    const checkbox = card.querySelector('input[type="checkbox"]');
                    checkbox.checked = group.table_ids.includes(
                        Number(card.dataset.tableId)
                    );
                });
            });

            pairingList.appendChild(button);
        });
    }

    [
        dateInput,
        timeInput,
        partyInput,
        areaInput,
        nearTv,
        avoidsBench,
        eating,
    ].filter(Boolean).forEach(control => {
        control.addEventListener("change", update);
        control.addEventListener("input", update);
    });

    update();
}


document.addEventListener("DOMContentLoaded", () => {
    setupCustomerLookup();
    setupBookingTimeValidation();
    setupKitchenWarning();
    setupDepositWarning();
    setupLargePartyDepositWarning();
    setupLargePartyFoodQuote();
    setupExtraDishes();
    setupLargePartyEndTime();
    setupLargePartyAreaFiltering();
    setupInquiryReminders();
    setupNormalTableAvailability();
});
