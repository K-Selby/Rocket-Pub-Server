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




function setupTableLayoutEditor() {
    const stage = document.getElementById("floor-plan-stage");
    const saveButton = document.getElementById("layout-save");

    if (!stage || !saveButton) return;

    const svg = document.getElementById("pairing-lines");
    const editMode = document.getElementById("layout-edit-mode");
    const selectedLabel = document.getElementById("selected-table-label");
    const shapeSelect = document.getElementById("layout-shape");
    const rotateLeft = document.getElementById("layout-rotate-left");
    const rotateRight = document.getElementById("layout-rotate-right");
    const fitButton = document.getElementById("layout-fit-view");
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
        pool_table: "Pool table",
        stairs: "Stairs",
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

    function rectRelativeToStage(element) {
        const stageRect = stage.getBoundingClientRect();
        const rect = element.getBoundingClientRect();

        return {
            x: rect.left - stageRect.left + rect.width / 2,
            y: rect.top - stageRect.top + rect.height / 2,
        };
    }

    function drawPairings() {
        if (!svg) return;

        svg.innerHTML = "";

        pairings.forEach(pairing => {
            const a = tableById(pairing.a);
            const b = tableById(pairing.b);

            if (!a || !b) return;

            const p1 = rectRelativeToStage(a);
            const p2 = rectRelativeToStage(b);

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

        const kind = element.dataset.kind;
        inspectorEmpty.hidden = true;
        shapeSelect.value = element.dataset.shape || "rectangle";

        if (kind === "table") {
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
            const size = Math.max(
                parseFloat(element.style.width || "90"),
                parseFloat(element.style.height || "60")
            );

            element.style.width = `${size}px`;
            element.style.height = `${size}px`;
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

    function makeInteractive(element) {
        element.addEventListener("pointerdown", event => {
            if (event.target.classList.contains("resize-handle")) {
                return;
            }

            selectElement(element);

            if (!editMode.checked) return;

            const startX = event.clientX;
            const startY = event.clientY;
            const startLeft = parseFloat(element.style.left || "0");
            const startTop = parseFloat(element.style.top || "0");

            element.setPointerCapture(event.pointerId);

            function move(moveEvent) {
                const dx = moveEvent.clientX - startX;
                const dy = moveEvent.clientY - startY;

                const maxLeft = stage.clientWidth - element.offsetWidth;
                const maxTop = stage.clientHeight - element.offsetHeight;

                element.style.left = `${Math.min(
                    Math.max(startLeft + dx, 0),
                    Math.max(maxLeft, 0)
                )}px`;

                element.style.top = `${Math.min(
                    Math.max(startTop + dy, 0),
                    Math.max(maxTop, 0)
                )}px`;

                drawPairings();
            }

            function finish() {
                element.removeEventListener("pointermove", move);
                element.removeEventListener("pointerup", finish);
                element.removeEventListener("pointercancel", finish);
            }

            element.addEventListener("pointermove", move);
            element.addEventListener("pointerup", finish);
            element.addEventListener("pointercancel", finish);
        });

        const handle = element.querySelector(".resize-handle");

        if (!handle) return;

        handle.addEventListener("pointerdown", event => {
            if (!editMode.checked) return;

            event.stopPropagation();
            selectElement(element);

            const startX = event.clientX;
            const startY = event.clientY;
            const startWidth = element.offsetWidth;
            const startHeight = element.offsetHeight;

            handle.setPointerCapture(event.pointerId);

            function resize(moveEvent) {
                let width = Math.max(
                    16,
                    Math.min(
                        1000,
                        startWidth + moveEvent.clientX - startX
                    )
                );

                let height = Math.max(
                    10,
                    Math.min(
                        800,
                        startHeight + moveEvent.clientY - startY
                    )
                );

                if (
                    element.dataset.shape === "square" ||
                    element.dataset.shape === "round"
                ) {
                    const size = Math.max(width, height);
                    width = size;
                    height = size;
                }

                element.style.width = `${width}px`;
                element.style.height = `${height}px`;
                drawPairings();
            }

            function finish() {
                handle.removeEventListener("pointermove", resize);
                handle.removeEventListener("pointerup", finish);
                handle.removeEventListener("pointercancel", finish);
            }

            handle.addEventListener("pointermove", resize);
            handle.addEventListener("pointerup", finish);
            handle.addEventListener("pointercancel", finish);
        });
    }

    allEditableElements().forEach(makeInteractive);

    shapeSelect.addEventListener("change", () => {
        if (selected) {
            setShape(selected, shapeSelect.value);
        }
    });

    rotateLeft.addEventListener("click", () => rotateSelected(-15));
    rotateRight.addEventListener("click", () => rotateSelected(15));

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

        const tableId = Number(selected.dataset.tableId);

        const response = await fetch(
            `/api/table-layout/table/${tableId}`,
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

        const objectId = Number(selected.dataset.objectId);

        const response = await fetch(
            `/api/floor-objects/${objectId}`,
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
            const objectType = button.dataset.addObject;

            const response = await fetch(
                "/api/floor-objects",
                {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        object_type: objectType,
                        x: 80 + Math.random() * 80,
                        y: 80 + Math.random() * 80,
                    }),
                }
            );

            const result = await response.json();

            if (!response.ok || !result.ok) {
                alert(result.error || "Could not add object.");
                return;
            }

            // Reload keeps the HTML/data structure simple and guarantees the
            // newly assigned database ID is represented everywhere.
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
                x: parseFloat(table.style.left || "0"),
                y: parseFloat(table.style.top || "0"),
                width: table.offsetWidth,
                height: table.offsetHeight,
                shape: table.dataset.shape || "rectangle",
                rotation: Number(table.dataset.rotation || 0),
            })),

            objects: objects.map(object => ({
                id: Number(object.dataset.objectId),
                x: parseFloat(object.style.left || "0"),
                y: parseFloat(object.style.top || "0"),
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

    fitButton.addEventListener("click", () => {
        stage.parentElement.scrollTo({
            left: 0,
            top: 0,
            behavior: "smooth",
        });
    });

    stage.addEventListener("pointerdown", event => {
        if (
            event.target === stage ||
            event.target.classList.contains("floor-plan-grid")
        ) {
            showNothingSelected();
        }
    });

    window.addEventListener("resize", drawPairings);
    drawPairings();
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
    setupTableLayoutEditor();
});
