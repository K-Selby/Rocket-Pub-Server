console.log("Pub Booking System loaded.");


/**
 * Normalise a phone number in the browser using the same basic rules as Flask.
 */
function normalisePhone(phone) {
    let cleaned = (phone || "").replace(/\D/g, "");

    if (cleaned.startsWith("44") && cleaned.length >= 12) {
        cleaned = "0" + cleaned.slice(2);
    }

    return cleaned;
}


/**
 * Refill saved preferences when an existing customer is recognised.
 *
 * Phone number is authoritative because two customers may share the same name.
 * An exact unique name match can also fill the phone number to speed up entry.
 */
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

        // Only autofill from name if it identifies exactly one saved customer.
        if (matches.length === 1) {
            applyCustomer(matches[0]);
        }
    });
}


/**
 * Show the kitchen warning for bookings later than 18:45.
 *
 * Sunday has a 19:30 kitchen close; all other days use 20:00.
 */
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

        // Appending T12:00 prevents timezone conversion from unexpectedly
        // moving the selected date to the previous/next day.
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


document.addEventListener("DOMContentLoaded", () => {
    setupCustomerLookup();
    setupKitchenWarning();
});
