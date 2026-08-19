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

    if (size <= 10) {
        return 0;
    }

    return Math.min(size * 5, 100);
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
        if (!customer) {
            message.hidden = true;
            return;
        }

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

        if (matches.length === 1) {
            applyCustomer(matches[0]);
        }
    });
}


function setupBookingTimeValidation() {
    const dateInput = document.getElementById("booking-date");
    const timeInput = document.getElementById("booking-time");

    if (!dateInput || !timeInput) return;

    function latestTime() {
        if (!dateInput.value) {
            return "19:30";
        }

        const date = new Date(dateInput.value + "T12:00:00");
        return date.getDay() === 0 ? "19:00" : "19:30";
    }

    function validateTime(showPopup = true) {
        if (!timeInput.value) return true;

        const latest = latestTime();
        const tooEarly = timeInput.value < "12:15";
        const tooLate = timeInput.value > latest;

        if (tooEarly || tooLate) {
            const latestDisplay = latest === "19:00" ? "7:00pm" : "7:30pm";
            timeInput.value = "";

            if (showPopup) {
                alert(
                    "The earliest available booking time is 12:15pm and " +
                    `the latest available time is ${latestDisplay}.`
                );
            }

            return false;
        }

        return true;
    }

    timeInput.addEventListener("change", () => validateTime(true));

    dateInput.addEventListener("change", () => {
        // If the date is changed to a Sunday, a previously valid 7:30pm time
        // should immediately be rejected and cleared.
        validateTime(true);
    });
}


function setupKitchenWarning() {
    const dateInput = document.getElementById("booking-date");
    const timeInput = document.getElementById("booking-time");
    const warning = document.getElementById("late-food-warning");

    if (!dateInput || !timeInput || !warning) return;

    function updateWarning() {
        const dateValue = dateInput.value;
        const timeValue = timeInput.value;

        if (!dateValue || !timeValue || timeValue <= "18:45") {
            warning.hidden = true;
            warning.textContent = "";
            return;
        }

        const selectedDate = new Date(dateValue + "T12:00:00");
        const isSunday = selectedDate.getDay() === 0;
        const closeTime = isSunday ? "7:30pm" : "8:00pm";

        warning.textContent =
            `Please let the customer know that the kitchen closes at ${closeTime}. ` +
            "Depending on how busy we are, they may need to order promptly " +
            "to make sure we are able to accept their food order.";

        warning.hidden = false;
    }

    dateInput.addEventListener("change", updateWarning);
    timeInput.addEventListener("change", updateWarning);
    updateWarning();
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
            paidInput.max = "";
            return;
        }

        warning.textContent =
            `A deposit of £${due.toFixed(2)} may be required. ` +
            "Please let the customer know that we will call them back to confirm the deposit.";

        warning.hidden = false;
        paymentField.hidden = false;
        paidInput.max = due.toFixed(2);
    }

    partyInput.addEventListener("input", update);
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
            paidInput.max = "";
            return;
        }

        warning.textContent =
            `If this enquiry proceeds, a deposit of £${due.toFixed(2)} may be required. ` +
            "The customer can be called back once the details are confirmed.";

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
        const rawPrice = selected ? selected.dataset.price : "";
        const price = rawPrice === "" ? null : Number(rawPrice);

        if (!catered || price === null || Number.isNaN(price)) {
            preview.textContent = "Not calculated";
            return;
        }

        preview.textContent = `£${(price * catered).toFixed(2)}`;
    }

    partyInput.addEventListener("input", update);
    cateredInput.addEventListener("input", update);
    optionSelect.addEventListener("change", update);
    update();
}


document.addEventListener("DOMContentLoaded", () => {
    setupCustomerLookup();
    setupBookingTimeValidation();
    setupKitchenWarning();
    setupDepositWarning();
    setupLargePartyDepositWarning();
    setupLargePartyFoodQuote();
});
