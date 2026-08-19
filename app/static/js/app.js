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

    const slider = document.getElementById("table-slider");
    const sliderLeft = document.getElementById("table-slider-left");
    const sliderRight = document.getElementById("table-slider-right");

    const cards = Array.from(document.querySelectorAll(".table-choice-card"));
    const mapStage = document.getElementById("booking-floor-plan-stage");
    const mapShell = document.getElementById("booking-floor-plan-shell");
    const zoomSurface = document.getElementById("booking-floor-plan-zoom-surface");
    const mapFit = document.getElementById("booking-map-fit");
    const mapTables = Array.from(document.querySelectorAll(".booking-map-table"));
    const pairingList = document.getElementById("pairing-suggestion-list");

    if (!form || !dateInput || !timeInput || !partyInput || !slider ||
        !cards.length || !mapStage || !mapShell || !zoomSurface || !pairingList) {
        return;
    }

    let availabilityById = new Map();

    const STATUS_ORDER = {
        ideal: 0,
        suitable: 1,
        available: 1,
        too_small: 2,
        unavailable: 3,
        large_party: 4,
    };

    const STATUS_TEXT = {
        ideal: "Ideal",
        suitable: "Available — larger than needed",
        available: "Available",
        too_small: "Too small alone",
        unavailable: "Unavailable",
        large_party: "Reserved for large party",
    };

    function cardForTable(id) {
        return document.querySelector(`.table-choice-card[data-table-id="${id}"]`);
    }

    function mapTableFor(id) {
        return document.querySelector(`.booking-map-table[data-table-id="${id}"]`);
    }

    function clearHoverHighlight() {
        cards.forEach(card => card.classList.remove("table-hover-focus"));
        mapTables.forEach(table => {
            table.classList.remove("booking-map-hover");
            table.classList.remove("booking-map-dimmed");
        });
    }

    function highlightTable(id) {
        clearHoverHighlight();

        const card = cardForTable(id);
        const mapTable = mapTableFor(id);

        if (card) card.classList.add("table-hover-focus");

        mapTables.forEach(table => {
            if (table === mapTable) {
                table.classList.add("booking-map-hover");
            } else {
                table.classList.add("booking-map-dimmed");
            }
        });
    }

    function syncSelectedVisuals() {
        cards.forEach(card => {
            const checkbox = card.querySelector('input[type="checkbox"]');
            const selected = Boolean(checkbox?.checked);

            card.classList.toggle("table-choice-selected", selected);

            const mapTable = mapTableFor(card.dataset.tableId);
            if (mapTable) {
                mapTable.classList.toggle("booking-map-selected", selected);
            }
        });
    }

    function applyStatusClasses(element, status) {
        element.classList.remove(
            "status-ideal",
            "status-suitable",
            "status-too-small",
            "status-unavailable",
            "status-large-party"
        );

        if (status === "ideal") {
            element.classList.add("status-ideal");
        } else if (status === "suitable" || status === "available") {
            element.classList.add("status-suitable");
        } else if (status === "too_small") {
            element.classList.add("status-too-small");
        } else if (status === "large_party") {
            element.classList.add("status-large-party");
        } else if (status === "unavailable") {
            element.classList.add("status-unavailable");
        }
    }

    function sortCards() {
        const party = Number(partyInput.value || 0);

        [...cards].sort((a, b) => {
            const aData = availabilityById.get(a.dataset.tableId);
            const bData = availabilityById.get(b.dataset.tableId);

            const statusDiff =
                (STATUS_ORDER[aData?.status || "available"] ?? 99) -
                (STATUS_ORDER[bData?.status || "available"] ?? 99);

            if (statusDiff !== 0) return statusDiff;

            const aWaste = Math.max(Number(a.dataset.capacity || 0) - party, 0);
            const bWaste = Math.max(Number(b.dataset.capacity || 0) - party, 0);

            if (aWaste !== bWaste) return aWaste - bWaste;

            return Number(a.dataset.number) - Number(b.dataset.number);
        }).forEach(card => slider.appendChild(card));
    }

    function fitMap() {
        const availableWidth = Math.max(mapShell.clientWidth - 20, 100);
        const availableHeight = Math.max(mapShell.clientHeight - 20, 100);

        const zoom = Math.max(
            Math.min(
                availableWidth / mapStage.offsetWidth,
                availableHeight / mapStage.offsetHeight,
                1
            ),
            0.25
        );

        mapStage.style.transform = `scale(${zoom})`;
        mapStage.style.transformOrigin = "top left";
        zoomSurface.style.width = `${mapStage.offsetWidth * zoom}px`;
        zoomSurface.style.height = `${mapStage.offsetHeight * zoom}px`;
        mapShell.scrollLeft = 0;
        mapShell.scrollTop = 0;
    }

    function updatePairingSuggestions(groups) {
        pairingList.innerHTML = "";

        groups.forEach(group => {
            if (group.table_ids.length <= 1) return;

            const button = document.createElement("button");
            button.type = "button";
            button.className = "pairing-option";
            button.textContent = `T${group.numbers.join(" + T")} · ${group.capacity} seats`;

            button.addEventListener("mouseenter", () => {
                clearHoverHighlight();

                group.table_ids.forEach(id => {
                    mapTableFor(id)?.classList.add("booking-map-hover");
                });

                mapTables.forEach(table => {
                    if (!group.table_ids.includes(Number(table.dataset.tableId))) {
                        table.classList.add("booking-map-dimmed");
                    }
                });
            });

            button.addEventListener("mouseleave", clearHoverHighlight);

            button.addEventListener("click", () => {
                cards.forEach(card => {
                    const checkbox = card.querySelector('input[type="checkbox"]');
                    const shouldSelect = group.table_ids.includes(Number(card.dataset.tableId));

                    if (!checkbox.disabled) {
                        checkbox.checked = shouldSelect;
                    }
                });

                syncSelectedVisuals();
            });

            pairingList.appendChild(button);
        });
    }

    async function updateAvailability() {
        if (!dateInput.value || !timeInput.value || !partyInput.value) {
            cards.forEach(card => {
                applyStatusClasses(card, "available");
                card.querySelector(".table-choice-status").textContent = "Enter booking details";
            });

            mapTables.forEach(table => applyStatusClasses(table, "available"));
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

        availabilityById = new Map(
            data.tables.map(table => [String(table.id), table])
        );

        cards.forEach(card => {
            const table = availabilityById.get(card.dataset.tableId);
            const checkbox = card.querySelector('input[type="checkbox"]');

            if (!table) return;

            applyStatusClasses(card, table.status);
            card.querySelector(".table-choice-status").textContent =
                STATUS_TEXT[table.status] || table.status;

            const unavailable =
                table.status === "unavailable" ||
                table.status === "large_party";

            checkbox.disabled = unavailable;
            if (unavailable) checkbox.checked = false;

            const mapTable = mapTableFor(card.dataset.tableId);

            if (mapTable) {
                applyStatusClasses(mapTable, table.status);
                mapTable.disabled = !table.available;
            }
        });

        sortCards();
        updatePairingSuggestions(data.groups || []);
        syncSelectedVisuals();
    }

    cards.forEach(card => {
        const checkbox = card.querySelector('input[type="checkbox"]');

        card.addEventListener("mouseenter", () => highlightTable(card.dataset.tableId));
        card.addEventListener("mouseleave", clearHoverHighlight);

        card.addEventListener("click", event => {
            if (event.target === checkbox || checkbox.disabled) return;

            event.preventDefault();
            checkbox.checked = !checkbox.checked;
            syncSelectedVisuals();
        });

        checkbox.addEventListener("change", syncSelectedVisuals);
    });

    mapTables.forEach(table => {
        table.addEventListener("mouseenter", () => {
            const id = table.dataset.tableId;
            highlightTable(id);

            const card = cardForTable(id);
            if (card) {
                card.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest",
                    inline: "center",
                });
            }
        });

        table.addEventListener("mouseleave", clearHoverHighlight);

        table.addEventListener("click", () => {
            const card = cardForTable(table.dataset.tableId);
            if (!card) return;

            const checkbox = card.querySelector('input[type="checkbox"]');
            if (!checkbox || checkbox.disabled) return;

            checkbox.checked = !checkbox.checked;
            syncSelectedVisuals();
        });
    });

    sliderLeft.addEventListener("click", () => {
        slider.scrollBy({
            left: -Math.max(slider.clientWidth * 0.75, 300),
            behavior: "smooth",
        });
    });

    sliderRight.addEventListener("click", () => {
        slider.scrollBy({
            left: Math.max(slider.clientWidth * 0.75, 300),
            behavior: "smooth",
        });
    });

    mapFit?.addEventListener("click", fitMap);

    [
        dateInput,
        timeInput,
        partyInput,
        areaInput,
        nearTv,
        avoidsBench,
        eating,
    ].filter(Boolean).forEach(control => {
        control.addEventListener("change", updateAvailability);
        control.addEventListener("input", updateAvailability);
    });

    window.addEventListener("resize", fitMap);

    syncSelectedVisuals();
    fitMap();
    updateAvailability();
}


function setupTableLayoutEditor() {
    const stage = document.getElementById("floor-plan-stage");
    const zoomSurface = document.getElementById("floor-plan-zoom-surface");
    const shell = document.getElementById("floor-plan-shell");
    const saveButton = document.getElementById("layout-save");

    if (!stage || !zoomSurface || !shell || !saveButton) return;

    const svg = document.getElementById("pairing-lines");
    const editMode = document.getElementById("layout-edit-mode");
    const selectedLabel = document.getElementById("selected-table-label");
    const shapeSelect = document.getElementById("layout-shape");
    const rotateLeft = document.getElementById("layout-rotate-left");
    const rotateRight = document.getElementById("layout-rotate-right");

    const zoomOut = document.getElementById("layout-zoom-out");
    const zoomIn = document.getElementById("layout-zoom-in");
    const zoomLabel = document.getElementById("layout-zoom-label");
    const fitButton = document.getElementById("layout-fit-view");

    const mapWidthInput = document.getElementById("floor-map-width");
    const mapHeightInput = document.getElementById("floor-map-height");
    const applyMapSize = document.getElementById("apply-map-size");
    const editorHeight = document.getElementById("editor-window-height");

    const layerControls = document.getElementById("object-layer-controls");
    const bringForward = document.getElementById("bring-forward");
    const sendBackward = document.getElementById("send-backward");

    const inspectorEmpty = document.getElementById("layout-inspector-empty");
    const tableInspector = document.getElementById("layout-table-inspector");
    const objectInspector = document.getElementById("layout-object-inspector");
    const pairingPanel = document.getElementById("table-pairing-panel");

    const inspectorNumber = document.getElementById("inspector-number");
    const inspectorCapacity = document.getElementById("inspector-capacity");
    const inspectorArea = document.getElementById("inspector-area");
    const inspectorNearTv = document.getElementById("inspector-near-tv");
    const inspectorBench = document.getElementById("inspector-bench");
    const inspectorAccessible = document.getElementById("inspector-accessible");
    const inspectorFood = document.getElementById("inspector-food-unsuitable");
    const inspectorActive = document.getElementById("inspector-active");

    const objectTypeBadge = document.getElementById("object-type-badge");
    const objectLabel = document.getElementById("object-label");
    const objectArea = document.getElementById("object-area");
    const duplicateObject = document.getElementById("duplicate-object");
    const deleteObject = document.getElementById("delete-object");

    const pairFirstButton = document.getElementById("pair-first");
    const pairCreateButton = document.getElementById("pair-create");
    const pairFirstLabel = document.getElementById("pair-first-label");
    const pairingList = document.getElementById("pairing-list");

    let selected = null;
    let firstPairTable = null;
    let currentZoom = 1;
    const MIN_ZOOM = 0.35;
    const MAX_ZOOM = 1.25;
    const ZOOM_STEP = 0.1;

    let pairings = Array.isArray(window.FLOOR_PAIRINGS)
        ? [...window.FLOOR_PAIRINGS]
        : [];

    const objectNames = {
        wall: "Wall",
        door: "Door / opening",
        bar: "Bar",
        pillar: "Pillar",
        tv: "TV",
        fixed_table: "Non-bookable table",
        label: "Label",
        area: "Area block",
    };

    function allEditableElements() {
        return Array.from(
            stage.querySelectorAll(".layout-table, .floor-object")
        );
    }

    function tableById(id) {
        return stage.querySelector(
            `.layout-table[data-table-id="${id}"]`
        );
    }

    function updateZoomSurfaceSize() {
        zoomSurface.style.width = `${stage.offsetWidth * currentZoom}px`;
        zoomSurface.style.height = `${stage.offsetHeight * currentZoom}px`;
    }

    function applyZoom(value, keepCentre = true) {
        const oldZoom = currentZoom;
        currentZoom = Math.max(
            MIN_ZOOM,
            Math.min(MAX_ZOOM, value)
        );

        let centreX = null;
        let centreY = null;

        if (keepCentre) {
            centreX = (shell.scrollLeft + shell.clientWidth / 2) / oldZoom;
            centreY = (shell.scrollTop + shell.clientHeight / 2) / oldZoom;
        }

        stage.style.transform = `scale(${currentZoom})`;
        stage.style.transformOrigin = "top left";

        updateZoomSurfaceSize();

        if (zoomLabel) {
            zoomLabel.textContent = `${Math.round(currentZoom * 100)}%`;
        }

        if (keepCentre && centreX !== null) {
            requestAnimationFrame(() => {
                shell.scrollLeft =
                    centreX * currentZoom - shell.clientWidth / 2;
                shell.scrollTop =
                    centreY * currentZoom - shell.clientHeight / 2;
            });
        }

        drawPairings();
    }

    function fitWholeMap() {
        const availableWidth = Math.max(shell.clientWidth - 32, 100);
        const availableHeight = Math.max(shell.clientHeight - 32, 100);

        const fit = Math.min(
            availableWidth / stage.offsetWidth,
            availableHeight / stage.offsetHeight,
            1
        );

        applyZoom(
            Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, fit)),
            false
        );

        shell.scrollLeft = 0;
        shell.scrollTop = 0;
    }

    function rectCentre(element) {
        return {
            x: element.offsetLeft + element.offsetWidth / 2,
            y: element.offsetTop + element.offsetHeight / 2,
        };
    }

    function drawPairings() {
        if (!svg) return;

        svg.innerHTML = "";

        pairings.forEach(pairing => {
            const a = tableById(pairing.a);
            const b = tableById(pairing.b);

            if (!a || !b) return;

            const p1 = rectCentre(a);
            const p2 = rectCentre(b);

            const line = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "line"
            );

            line.setAttribute("x1", p1.x);
            line.setAttribute("y1", p1.y);
            line.setAttribute("x2", p2.x);
            line.setAttribute("y2", p2.y);
            line.setAttribute("class", "pairing-line");

            svg.appendChild(line);
        });
    }

    function clearSelectionStyles() {
        allEditableElements().forEach(item => {
            item.classList.remove(
                "layout-table-selected",
                "floor-object-selected"
            );
        });
    }

    function showNothingSelected() {
        selected = null;
        selectedLabel.textContent = "None";
        inspectorEmpty.hidden = false;
        tableInspector.hidden = true;
        objectInspector.hidden = true;
        pairingPanel.hidden = true;
        layerControls.hidden = true;
    }

    function selectElement(element) {
        clearSelectionStyles();
        selected = element;

        if (!element) {
            showNothingSelected();
            return;
        }

        inspectorEmpty.hidden = true;
        shapeSelect.value = element.dataset.shape || "rectangle";

        if (element.dataset.kind === "table") {
            element.classList.add("layout-table-selected");
            selectedLabel.textContent = `Table ${element.dataset.number}`;

            tableInspector.hidden = false;
            objectInspector.hidden = true;
            pairingPanel.hidden = false;
            layerControls.hidden = true;

            inspectorNumber.value = element.dataset.number;
            inspectorCapacity.value = element.dataset.capacity;
            inspectorArea.value = element.dataset.areaId;
            inspectorNearTv.checked = element.dataset.nearTv === "1";
            inspectorBench.checked = element.dataset.hasBench === "1";
            inspectorAccessible.checked = element.dataset.accessible === "1";
            inspectorFood.checked = element.dataset.unsuitableFood === "1";
            inspectorActive.checked = element.dataset.active === "1";
        } else {
            element.classList.add("floor-object-selected");

            const type = element.dataset.objectType;
            selectedLabel.textContent =
                `${objectNames[type] || "Object"}: ${element.dataset.label || ""}`;

            tableInspector.hidden = true;
            objectInspector.hidden = false;
            pairingPanel.hidden = true;
            layerControls.hidden = false;

            objectTypeBadge.textContent =
                objectNames[type] || type.replaceAll("_", " ");
            objectLabel.value = element.dataset.label || "";
            objectArea.value = element.dataset.areaId || "";
        }
    }

    function setShape(element, shape) {
        if (!element) return;

        element.classList.remove(
            "shape-rectangle",
            "shape-square",
            "shape-round",
            "shape-oval"
        );

        element.classList.add(`shape-${shape}`);
        element.dataset.shape = shape;

        if (shape === "square" || shape === "round") {
            const maxWidth = stage.clientWidth - element.offsetLeft;
            const maxHeight = stage.clientHeight - element.offsetTop;

            const size = Math.min(
                Math.max(element.offsetWidth, element.offsetHeight),
                maxWidth,
                maxHeight
            );

            element.style.width = `${Math.max(size, 16)}px`;
            element.style.height = `${Math.max(size, 16)}px`;
        }

        drawPairings();
    }

    function rotateSelected(amount) {
        if (!selected) return;

        const current = Number(selected.dataset.rotation || 0);
        const next = (current + amount + 360) % 360;

        selected.dataset.rotation = String(next);
        selected.style.transform = `rotate(${next}deg)`;
        drawPairings();
    }

    function rotatedVisualBounds(element) {
        /*
         * CSS rotation happens around the centre of the element. offsetLeft /
         * offsetWidth still describe the unrotated box, which is why a long
         * wall rotated 90° previously appeared unable to reach the left edge.
         *
         * Calculate the axis-aligned visual box after rotation, then return
         * the legal offsetLeft/offsetTop range needed to keep that VISUAL box
         * inside the map.
         */
        const width = element.offsetWidth;
        const height = element.offsetHeight;
        const degrees = Number(element.dataset.rotation || 0);
        const radians = degrees * Math.PI / 180;

        const cos = Math.abs(Math.cos(radians));
        const sin = Math.abs(Math.sin(radians));

        const visualWidth = width * cos + height * sin;
        const visualHeight = width * sin + height * cos;

        // Visual box is centred on the original layout box.
        const visualLeftOffset = (width - visualWidth) / 2;
        const visualTopOffset = (height - visualHeight) / 2;

        return {
            minLeft: -visualLeftOffset,
            maxLeft:
                stage.clientWidth -
                visualLeftOffset -
                visualWidth,

            minTop: -visualTopOffset,
            maxTop:
                stage.clientHeight -
                visualTopOffset -
                visualHeight,

            visualWidth,
            visualHeight,
        };
    }

    function clampElementToMap(element) {
        const bounds = rotatedVisualBounds(element);

        // If an object is visually larger than the map in one dimension,
        // centre it in that dimension rather than producing unstable bounds.
        const minLeft = Math.min(bounds.minLeft, bounds.maxLeft);
        const maxLeft = Math.max(bounds.minLeft, bounds.maxLeft);
        const minTop = Math.min(bounds.minTop, bounds.maxTop);
        const maxTop = Math.max(bounds.minTop, bounds.maxTop);

        element.style.left =
            `${Math.min(Math.max(element.offsetLeft, minLeft), maxLeft)}px`;

        element.style.top =
            `${Math.min(Math.max(element.offsetTop, minTop), maxTop)}px`;
    }


    function makeInteractive(element) {
        element.addEventListener("pointerdown", event => {
            if (event.button !== 0) return;
            if (event.target.classList.contains("resize-handle")) return;

            selectElement(element);

            if (!editMode.checked) return;

            event.preventDefault();

            const startX = event.clientX;
            const startY = event.clientY;
            const startLeft = element.offsetLeft;
            const startTop = element.offsetTop;

            function move(moveEvent) {
                const dx = (moveEvent.clientX - startX) / currentZoom;
                const dy = (moveEvent.clientY - startY) / currentZoom;

                const bounds = rotatedVisualBounds(element);

                const minLeft = Math.min(
                    bounds.minLeft,
                    bounds.maxLeft
                );
                const maxLeft = Math.max(
                    bounds.minLeft,
                    bounds.maxLeft
                );
                const minTop = Math.min(
                    bounds.minTop,
                    bounds.maxTop
                );
                const maxTop = Math.max(
                    bounds.minTop,
                    bounds.maxTop
                );

                element.style.left =
                    `${Math.min(
                        Math.max(startLeft + dx, minLeft),
                        maxLeft
                    )}px`;

                element.style.top =
                    `${Math.min(
                        Math.max(startTop + dy, minTop),
                        maxTop
                    )}px`;

                drawPairings();
            }

            function finish() {
                window.removeEventListener("pointermove", move);
                window.removeEventListener("pointerup", finish);
                window.removeEventListener("pointercancel", finish);
            }

            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", finish);
            window.addEventListener("pointercancel", finish);
        });

        const handle = element.querySelector(".resize-handle");

        if (!handle) return;

        handle.addEventListener("pointerdown", event => {
            if (!editMode.checked || event.button !== 0) return;

            event.preventDefault();
            event.stopPropagation();
            selectElement(element);

            const startX = event.clientX;
            const startY = event.clientY;
            const startWidth = element.offsetWidth;
            const startHeight = element.offsetHeight;

            function resize(moveEvent) {
                const dx = (moveEvent.clientX - startX) / currentZoom;
                const dy = (moveEvent.clientY - startY) / currentZoom;

                const maxWidth = Math.max(
                    stage.clientWidth - element.offsetLeft,
                    16
                );
                const maxHeight = Math.max(
                    stage.clientHeight - element.offsetTop,
                    10
                );

                let width = Math.min(
                    Math.max(startWidth + dx, 16),
                    maxWidth
                );

                let height = Math.min(
                    Math.max(startHeight + dy, 10),
                    maxHeight
                );

                if (
                    element.dataset.shape === "square" ||
                    element.dataset.shape === "round"
                ) {
                    const size = Math.min(
                        Math.max(width, height),
                        maxWidth,
                        maxHeight
                    );
                    width = size;
                    height = size;
                }

                element.style.width = `${width}px`;
                element.style.height = `${height}px`;

                // Rotation changes the visual footprint. Re-clamp after every
                // resize so walls/objects remain able to touch map edges
                // without visually spilling outside the map.
                clampElementToMap(element);

                drawPairings();
            }

            function finish() {
                window.removeEventListener("pointermove", resize);
                window.removeEventListener("pointerup", finish);
                window.removeEventListener("pointercancel", finish);
            }

            window.addEventListener("pointermove", resize);
            window.addEventListener("pointerup", finish);
            window.addEventListener("pointercancel", finish);
        });
    }

    allEditableElements().forEach(makeInteractive);

    shapeSelect.addEventListener("change", () => {
        if (selected) setShape(selected, shapeSelect.value);
    });

    rotateLeft.addEventListener("click", () => rotateSelected(-15));
    rotateRight.addEventListener("click", () => rotateSelected(15));

    zoomOut.addEventListener("click", () => {
        applyZoom(currentZoom - ZOOM_STEP);
    });

    zoomIn.addEventListener("click", () => {
        applyZoom(currentZoom + ZOOM_STEP);
    });

    fitButton.addEventListener("click", fitWholeMap);

    editorHeight.addEventListener("input", () => {
        shell.style.height = `${editorHeight.value}px`;
        shell.style.maxHeight = "none";
    });

    applyMapSize.addEventListener("click", () => {
        const width = Math.max(
            600,
            Math.min(3000, Number(mapWidthInput.value || 1200))
        );

        const height = Math.max(
            400,
            Math.min(2200, Number(mapHeightInput.value || 760))
        );

        stage.style.width = `${width}px`;
        stage.style.height = `${height}px`;

        mapWidthInput.value = width;
        mapHeightInput.value = height;

        // Keep every existing item fully inside the newly sized map.
        allEditableElements().forEach(element => {
            if (element.offsetWidth > width) {
                element.style.width = `${width}px`;
            }

            if (element.offsetHeight > height) {
                element.style.height = `${height}px`;
            }

            clampElementToMap(element);
        });

        updateZoomSurfaceSize();
        drawPairings();
    });

    bringForward.addEventListener("click", () => {
        if (!selected || selected.dataset.kind !== "object") return;

        const next = Math.min(
            Number(selected.dataset.zIndex || 1) + 1,
            100
        );

        selected.dataset.zIndex = String(next);
        selected.style.zIndex = next;
    });

    sendBackward.addEventListener("click", () => {
        if (!selected || selected.dataset.kind !== "object") return;

        const next = Math.max(
            Number(selected.dataset.zIndex || 1) - 1,
            -50
        );

        selected.dataset.zIndex = String(next);
        selected.style.zIndex = next;
    });

    tableInspector.addEventListener("submit", async event => {
        event.preventDefault();

        if (!selected || selected.dataset.kind !== "table") return;

        const response = await fetch(
            `/api/table-layout/table/${selected.dataset.tableId}`,
            {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    number: inspectorNumber.value,
                    capacity: Number(inspectorCapacity.value),
                    area_id: Number(inspectorArea.value),
                    near_tv: inspectorNearTv.checked,
                    has_bench: inspectorBench.checked,
                    accessible: inspectorAccessible.checked,
                    unsuitable_for_food: inspectorFood.checked,
                    active: inspectorActive.checked,
                }),
            }
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert(result.error || "Could not update table.");
            return;
        }

        selected.dataset.number = inspectorNumber.value;
        selected.dataset.capacity = inspectorCapacity.value;
        selected.dataset.areaId = inspectorArea.value;
        selected.dataset.areaName =
            inspectorArea.options[inspectorArea.selectedIndex].textContent;
        selected.dataset.nearTv = inspectorNearTv.checked ? "1" : "0";
        selected.dataset.hasBench = inspectorBench.checked ? "1" : "0";
        selected.dataset.accessible = inspectorAccessible.checked ? "1" : "0";
        selected.dataset.unsuitableFood = inspectorFood.checked ? "1" : "0";
        selected.dataset.active = inspectorActive.checked ? "1" : "0";

        selected.classList.toggle(
            "layout-table-inactive",
            !inspectorActive.checked
        );

        selected.querySelector("strong").textContent =
            `T${inspectorNumber.value}`;
        selected.querySelector("span").textContent =
            `${inspectorCapacity.value} seats`;
        selected.querySelector("small").textContent =
            inspectorArea.options[inspectorArea.selectedIndex].textContent;

        selectedLabel.textContent = `Table ${inspectorNumber.value}`;
    });

    objectInspector.addEventListener("submit", async event => {
        event.preventDefault();

        if (!selected || selected.dataset.kind !== "object") return;

        const response = await fetch(
            `/api/floor-objects/${selected.dataset.objectId}`,
            {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    label: objectLabel.value,
                    area_id: objectArea.value || null,
                }),
            }
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert(result.error || "Could not update object.");
            return;
        }

        selected.dataset.label = objectLabel.value;
        selected.dataset.areaId = objectArea.value || "";

        const label = selected.querySelector(".floor-object-label");
        if (label) label.textContent = objectLabel.value;

        selectElement(selected);
    });

    duplicateObject.addEventListener("click", async () => {
        if (!selected || selected.dataset.kind !== "object") return;

        const response = await fetch(
            `/api/floor-objects/${selected.dataset.objectId}/duplicate`,
            {method: "POST"}
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert("Could not duplicate object.");
            return;
        }

        await saveLayout();
        window.location.reload();
    });

    deleteObject.addEventListener("click", async () => {
        if (!selected || selected.dataset.kind !== "object") return;

        if (!confirm("Delete this floor-plan object?")) return;

        const response = await fetch(
            `/api/floor-objects/${selected.dataset.objectId}`,
            {method: "DELETE"}
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert("Could not delete object.");
            return;
        }

        selected.remove();
        showNothingSelected();
    });

    document.querySelectorAll("[data-add-object]").forEach(button => {
        button.addEventListener("click", async () => {
            /*
             * Adding an object reloads the editor so the new database ID can
             * be represented in the DOM. Save all current positions FIRST so
             * no unsaved drag/resize work is lost during that reload.
             */
            const currentLayout = await saveLayout();

            if (!currentLayout.ok) {
                alert(
                    "The current layout could not be saved, so the new object " +
                    "was not added."
                );
                return;
            }

            const response = await fetch(
                "/api/floor-objects",
                {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        object_type: button.dataset.addObject,
                        x: 50,
                        y: 50,
                    }),
                }
            );

            const result = await response.json();

            if (!response.ok || !result.ok) {
                alert(result.error || "Could not add object.");
                return;
            }

            window.location.reload();
        });
    });

    pairFirstButton.addEventListener("click", () => {
        if (!selected || selected.dataset.kind !== "table") {
            alert("Select a bookable table first.");
            return;
        }

        firstPairTable = Number(selected.dataset.tableId);
        pairFirstLabel.textContent = `T${selected.dataset.number}`;
    });

    pairCreateButton.addEventListener("click", async () => {
        if (
            !selected ||
            selected.dataset.kind !== "table" ||
            !firstPairTable
        ) {
            alert("Set the first table, then select the second table.");
            return;
        }

        const second = Number(selected.dataset.tableId);

        if (second === firstPairTable) {
            alert("Choose a different second table.");
            return;
        }

        const response = await fetch(
            "/api/table-layout/pair",
            {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    table_a_id: firstPairTable,
                    table_b_id: second,
                }),
            }
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert(result.error || "Could not create pairing.");
            return;
        }

        window.location.reload();
    });

    pairingList?.addEventListener("click", async event => {
        const button = event.target.closest(".delete-pairing");

        if (!button) return;

        const pairingId = button.dataset.pairingId;

        const response = await fetch(
            `/api/table-layout/pair/${pairingId}`,
            {method: "DELETE"}
        );

        const result = await response.json();

        if (!response.ok || !result.ok) {
            alert(result.error || "Could not remove pairing.");
            return;
        }

        pairings = pairings.filter(
            pairing => String(pairing.id) !== String(pairingId)
        );

        button.closest(".pairing-row")?.remove();
        drawPairings();
    });

    async function saveLayout() {
        const tables = Array.from(
            stage.querySelectorAll(".layout-table")
        );

        const objects = Array.from(
            stage.querySelectorAll(".floor-object")
        );

        const payload = {
            canvas_width: stage.clientWidth,
            canvas_height: stage.clientHeight,

            tables: tables.map(table => ({
                id: Number(table.dataset.tableId),
                x: table.offsetLeft,
                y: table.offsetTop,
                width: table.offsetWidth,
                height: table.offsetHeight,
                shape: table.dataset.shape || "rectangle",
                rotation: Number(table.dataset.rotation || 0),
            })),

            objects: objects.map(object => ({
                id: Number(object.dataset.objectId),
                x: object.offsetLeft,
                y: object.offsetTop,
                width: object.offsetWidth,
                height: object.offsetHeight,
                shape: object.dataset.shape || "rectangle",
                rotation: Number(object.dataset.rotation || 0),
                z_index: Number(object.dataset.zIndex || 1),
            })),
        };

        const response = await fetch(
            "/api/table-layout/save",
            {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            }
        );

        return response.json();
    }

    saveButton.addEventListener("click", async () => {
        const result = await saveLayout();

        if (!result.ok) {
            alert("Could not save the floor plan.");
            return;
        }

        const original = saveButton.textContent;
        saveButton.textContent = "Saved";

        setTimeout(() => {
            saveButton.textContent = original;
        }, 1200);
    });

    stage.addEventListener("pointerdown", event => {
        if (
            event.target === stage ||
            event.target.classList.contains("floor-plan-grid")
        ) {
            showNothingSelected();
        }
    });

    window.addEventListener("resize", () => {
        updateZoomSurfaceSize();
        drawPairings();
    });

    shell.style.height = `${editorHeight.value}px`;
    shell.style.maxHeight = "none";
    applyZoom(1, false);
    drawPairings();
}




function setupDashboardBookingStates() {
    const stateRoot = document.getElementById("dashboard-booking-state");
    const rows = Array.from(
        document.querySelectorAll(".dashboard-booking-row")
    );

    if (!stateRoot || !rows.length) return;

    const dashboardDate = stateRoot.dataset.dashboardDate;

    function localDateString(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    function bookingTimes(row) {
        const [hours, minutes] = row.dataset.startTime
            .split(":")
            .map(Number);

        const start = new Date(`${row.dataset.bookingDate}T00:00:00`);
        start.setHours(hours, minutes, 0, 0);

        const end = new Date(
            start.getTime() +
            Number(row.dataset.duration || 150) * 60 * 1000
        );

        return {start, end};
    }

    function setState(row, state) {
        row.classList.remove(
            "booking-state-upcoming",
            "booking-state-active",
            "booking-state-finished"
        );

        row.classList.add(`booking-state-${state}`);

        const label = row.querySelector(".dashboard-booking-state-label");
        const finishForm = row.querySelector(".finish-booking-form");

        if (state === "upcoming") {
            if (label) label.textContent = "Upcoming";
            if (finishForm) finishForm.hidden = true;
        } else if (state === "active") {
            if (label) label.textContent = "Here now";
            if (finishForm) finishForm.hidden = false;
        } else {
            if (label) label.textContent =
                row.dataset.completed === "1" ? "Left" : "Finished";
            if (finishForm) finishForm.hidden = true;
        }
    }

    function updateStates() {
        const now = new Date();
        const today = localDateString(now);

        rows.forEach(row => {
            if (row.dataset.completed === "1") {
                setState(row, "finished");
                return;
            }

            const rowDate = row.dataset.bookingDate;
            const {start, end} = bookingTimes(row);

            if (rowDate < today) {
                setState(row, "finished");
                return;
            }

            if (rowDate > today) {
                setState(row, "upcoming");
                return;
            }

            if (now < start) {
                setState(row, "upcoming");
            } else if (now < end) {
                setState(row, "active");
            } else {
                setState(row, "finished");
            }
        });
    }

    updateStates();

    // Keep today's dashboard changing automatically as bookings begin/end.
    if (dashboardDate === localDateString(new Date())) {
        window.setInterval(updateStates, 30000);
    }
}



function setupDashboardFloorMap() {
    const stage = document.getElementById("dashboard-floor-stage");
    const shell = document.getElementById("dashboard-floor-shell");
    const zoomSurface = document.getElementById(
        "dashboard-floor-zoom-surface"
    );
    const fitButton = document.getElementById("dashboard-map-fit");
    const tooltip = document.getElementById("dashboard-map-tooltip");

    if (!stage || !shell || !zoomSurface || !tooltip) return;

    const tableButtons = Array.from(
        stage.querySelectorAll(".dashboard-map-table")
    );

    const bookingsByTable = window.DASHBOARD_TABLE_BOOKINGS || {};
    const largePartiesByTable =
        window.DASHBOARD_LARGE_PARTY_TABLES || {};

    function fitMap() {
        /*
         * Dashboard map should use the full card width. Previously the zoom
         * was also limited by the viewer height, which made a wide floor plan
         * shrink unnecessarily and left a large empty strip on the right.
         */
        const availableWidth = Math.max(shell.clientWidth - 20, 100);

        const zoom = Math.max(
            Math.min(
                availableWidth / stage.offsetWidth,
                1
            ),
            0.25
        );

        const scaledWidth = stage.offsetWidth * zoom;
        const scaledHeight = stage.offsetHeight * zoom;

        stage.style.transform = `scale(${zoom})`;
        stage.style.transformOrigin = "top left";

        zoomSurface.style.width = `${scaledWidth}px`;
        zoomSurface.style.height = `${scaledHeight}px`;

        /*
         * Let the dashboard viewer follow the fitted map height instead of
         * forcing the map into a fixed-height viewport.
         */
        shell.style.height = `${scaledHeight + 20}px`;
        shell.scrollLeft = 0;
        shell.scrollTop = 0;
    }

    function tooltipHtml(tableNumber, bookings, largeParties) {
        const count = bookings.length;

        const largePartyRows = largeParties.map(party => `
            <div class="dashboard-tooltip-large-party">
                <div class="dashboard-tooltip-lp-label">
                    Large party reservation
                </div>
                <div>
                    <strong>${party.time_text}</strong>
                    <span>${party.customer_name}</span>
                </div>
                <small>
                    ${party.party_size} people · ${party.occasion}
                    · ${party.status}
                </small>
            </div>
        `).join("");

        const bookingRows = bookings.map(booking => `
            <div class="dashboard-tooltip-booking">
                <div>
                    <strong>
                        ${booking.start_time}–${booking.end_time}
                    </strong>
                    <span>
                        ${booking.customer_name}
                    </span>
                </div>
                <small>
                    ${booking.party_size} people
                    · ${booking.is_eating_food ? "Eating" : "Drinks only"}
                </small>
            </div>
        `).join("");

        if (!count && !largeParties.length) {
            return `
                <div class="dashboard-tooltip-title">
                    Table ${tableNumber}
                </div>
                <div class="dashboard-tooltip-empty">
                    No bookings on this day
                </div>
            `;
        }

        return `
            <div class="dashboard-tooltip-title">
                Table ${tableNumber}
                <span>
                    ${largeParties.length
                        ? "Large party reserved"
                        : `${count} booking${count === 1 ? "" : "s"}`}
                </span>
            </div>
            ${largePartyRows}
            ${bookingRows}
        `;
    }

    function showTooltip(button) {
        const tableId = button.dataset.tableId;
        const tableNumber = button.dataset.tableNumber;
        const bookings = bookingsByTable[String(tableId)] || [];
        const largeParties =
            largePartiesByTable[String(tableId)] || [];

        tooltip.innerHTML = tooltipHtml(
            tableNumber,
            bookings,
            largeParties
        );
        tooltip.hidden = false;

        /*
         * Position in unscaled floor-plan coordinates so the tooltip moves
         * with the map correctly when the whole plan is fitted/scaled.
         */
        const buttonCentreX =
            button.offsetLeft + button.offsetWidth / 2;

        let left =
            buttonCentreX - tooltip.offsetWidth / 2;

        left = Math.max(
            8,
            Math.min(
                left,
                stage.offsetWidth - tooltip.offsetWidth - 8
            )
        );

        let top =
            button.offsetTop - tooltip.offsetHeight - 12;

        if (top < 8) {
            top =
                button.offsetTop + button.offsetHeight + 12;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    function hideTooltip() {
        tooltip.hidden = true;
    }

    tableButtons.forEach(button => {
        button.addEventListener("mouseenter", () => {
            tableButtons.forEach(other => {
                if (other !== button) {
                    other.classList.add("dashboard-map-table-dimmed");
                }
            });

            button.classList.add("dashboard-map-table-hover");
            showTooltip(button);
        });

        button.addEventListener("mouseleave", () => {
            tableButtons.forEach(other => {
                other.classList.remove("dashboard-map-table-dimmed");
            });

            button.classList.remove("dashboard-map-table-hover");
            hideTooltip();
        });

        button.addEventListener("focus", () => showTooltip(button));
        button.addEventListener("blur", hideTooltip);
    });

    fitButton?.addEventListener("click", fitMap);
    window.addEventListener("resize", fitMap);

    fitMap();
}


function setupReadOnlyTableMap() {
    const stage = document.getElementById("readonly-map-stage");
    const shell = document.getElementById("readonly-map-shell");
    const zoomSurface = document.getElementById("readonly-map-zoom-surface");
    const tooltip = document.getElementById("readonly-map-tooltip");
    const fitButton = document.getElementById("readonly-map-fit");

    if (!stage || !shell || !zoomSurface || !tooltip) return;

    const tables = Array.from(
        stage.querySelectorAll(".readonly-map-table")
    );

    function fitMap() {
        const availableWidth = Math.max(shell.clientWidth - 20, 100);
        const availableHeight = Math.max(shell.clientHeight - 20, 100);

        const zoom = Math.max(
            Math.min(
                availableWidth / stage.offsetWidth,
                availableHeight / stage.offsetHeight,
                1
            ),
            0.25
        );

        stage.style.transform = `scale(${zoom})`;
        stage.style.transformOrigin = "top left";
        zoomSurface.style.width = `${stage.offsetWidth * zoom}px`;
        zoomSurface.style.height = `${stage.offsetHeight * zoom}px`;
        shell.scrollLeft = 0;
        shell.scrollTop = 0;
    }

    function showTooltip(table) {
        tooltip.innerHTML = `
            <div class="readonly-tooltip-title">
                Table ${table.dataset.number}
                <span>${table.dataset.capacity} seats</span>
            </div>
            <div><strong>Area:</strong> ${table.dataset.area}</div>
            <div><strong>Near TV:</strong> ${table.dataset.nearTv}</div>
            <div><strong>Bench:</strong> ${table.dataset.bench}</div>
            <div><strong>Accessible:</strong> ${table.dataset.accessible}</div>
            <div><strong>Food last resort:</strong> ${table.dataset.foodLastResort}</div>
        `;

        tooltip.hidden = false;

        let left =
            table.offsetLeft +
            table.offsetWidth / 2 -
            tooltip.offsetWidth / 2;

        left = Math.max(
            8,
            Math.min(left, stage.offsetWidth - tooltip.offsetWidth - 8)
        );

        let top = table.offsetTop - tooltip.offsetHeight - 10;

        if (top < 8) {
            top = table.offsetTop + table.offsetHeight + 10;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    tables.forEach(table => {
        table.addEventListener("mouseenter", () => {
            table.classList.add("readonly-map-table-hover");
            showTooltip(table);
        });

        table.addEventListener("mouseleave", () => {
            table.classList.remove("readonly-map-table-hover");
            tooltip.hidden = true;
        });

        table.addEventListener("focus", () => showTooltip(table));
        table.addEventListener("blur", () => {
            tooltip.hidden = true;
        });
    });

    fitButton?.addEventListener("click", fitMap);
    window.addEventListener("resize", fitMap);
    fitMap();
}


function setupExclusiveNavMenus() {
    const menus = Array.from(document.querySelectorAll("details.nav-menu"));

    menus.forEach(menu => {
        menu.addEventListener("toggle", () => {
            if (!menu.open) return;

            menus.forEach(other => {
                if (other !== menu) {
                    other.open = false;
                }
            });
        });
    });

    document.addEventListener("click", event => {
        if (event.target.closest("details.nav-menu")) return;
        menus.forEach(menu => {
            menu.open = false;
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    setupExclusiveNavMenus();
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
    setupTableLayoutEditor();
    setupDashboardFloorMap();
    setupDashboardBookingStates();
    setupReadOnlyTableMap();
});
