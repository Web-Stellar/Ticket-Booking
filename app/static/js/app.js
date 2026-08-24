// EventMaster Main Application Script
let currentUser = null;
let currentAuthToken = localStorage.getItem("token") || null;
let currentEvent = null;
let currentSeatsMap = [];
let selectedSeatIds = [];
let activeHoldTimer = null;
let holdExpirationTime = null;
let socket = null;

// Initialize App
document.addEventListener("DOMContentLoaded", async () => {
    if (currentAuthToken) {
        await fetchCurrentUser();
    } else {
        // Quick auto-login as customer by default for seamless experience
        await quickLogin("john@example.com", "cust123");
    }
    await loadEvents();
});

// --- Auth Functions ---
async function fetchCurrentUser() {
    try {
        const res = await fetch("/api/auth/me", {
            headers: { "Authorization": `Bearer ${currentAuthToken}` }
        });
        if (res.ok) {
            currentUser = await res.json();
            updateAuthUI();
        } else {
            logout();
        }
    } catch (e) {
        console.error("Auth verify error:", e);
    }
}

async function quickLogin(email, password) {
    try {
        const res = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (res.ok) {
            currentAuthToken = data.access_token;
            localStorage.setItem("token", currentAuthToken);
            currentUser = { id: data.user_id, email: data.email, name: data.name, role: data.role };
            updateAuthUI();
            showNotification(`Logged in as ${data.name} (${data.role})`, "success");
            
            // Refresh views
            if (currentEvent) loadSeatMap(currentEvent.id);
            if (currentUser.role === "ORGANISER" || currentUser.role === "ADMIN") {
                loadOrganiserSummary();
            }
        } else {
            showNotification(data.detail || "Login failed", "error");
        }
    } catch (e) {
        showNotification("Network error during login", "error");
    }
}

function updateAuthUI() {
    const userInfoBar = document.getElementById("userInfoBar");
    const loginBtnNav = document.getElementById("loginBtnNav");
    const userName = document.getElementById("userName");
    const userRole = document.getElementById("userRole");
    const orgTabBtn = document.getElementById("organiserTabBtn");
    const adminTabBtn = document.getElementById("adminTabBtn");

    if (currentUser) {
        userInfoBar.classList.remove("hidden");
        userInfoBar.classList.add("flex");
        loginBtnNav.classList.add("hidden");

        userName.innerText = currentUser.name;
        userRole.innerText = currentUser.role;

        if (currentUser.role === "ORGANISER" || currentUser.role === "ADMIN") {
            orgTabBtn.classList.remove("hidden");
        } else {
            orgTabBtn.classList.add("hidden");
        }

        if (currentUser.role === "ADMIN") {
            adminTabBtn.classList.remove("hidden");
        } else {
            adminTabBtn.classList.add("hidden");
        }
    } else {
        userInfoBar.classList.add("hidden");
        loginBtnNav.classList.remove("hidden");
        orgTabBtn.classList.add("hidden");
        adminTabBtn.classList.add("hidden");
    }
}

function logout() {
    currentAuthToken = null;
    currentUser = null;
    localStorage.removeItem("token");
    updateAuthUI();
    showNotification("Logged out successfully", "info");
    switchTab('eventsTab');
}

// --- Navigation Tabs ---
function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('border-blue-500', 'text-blue-400');
        btn.classList.add('border-transparent', 'text-slate-400');
    });

    const activeTab = document.getElementById(tabId);
    if (activeTab) activeTab.classList.remove('hidden');

    const activeBtn = document.getElementById(`tab-${tabId}`);
    if (activeBtn) {
        activeBtn.classList.remove('border-transparent', 'text-slate-400');
        activeBtn.classList.add('border-blue-500', 'text-blue-400');
    }

    if (tabId === 'bookingsTab') loadMyBookings();
    if (tabId === 'waitlistTab') loadMyWaitlist();
    if (tabId === 'organiserTab') loadOrganiserSummary();
    if (tabId === 'emailsTab') loadEmailInbox();
}

// --- Events List & Selection ---
async function loadEvents(category = "") {
    try {
        let url = "/api/events";
        if (category) url += `?category=${encodeURIComponent(category)}`;
        const res = await fetch(url);
        const events = await res.json();

        const container = document.getElementById("eventsList");
        document.getElementById("eventCountBadge").innerText = `${events.length} event(s)`;

        if (events.length === 0) {
            container.innerHTML = `<div class="p-6 text-center text-slate-500 border border-slate-800 rounded-xl">No events found.</div>`;
            return;
        }

        container.innerHTML = events.map(evt => {
            const isSoldOut = evt.available_seats === 0;
            const pricesStr = evt.prices.map(p => `${p.category}: $${p.price}`).join(" | ");

            return `
            <div onclick="selectEvent('${evt.id}')" class="p-4 bg-slate-800 hover:bg-slate-750 border border-slate-700 rounded-xl cursor-pointer transition shadow hover:shadow-md space-y-2">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold text-blue-400 uppercase tracking-wide">${evt.category}</span>
                    <span class="text-[11px] ${isSoldOut ? 'bg-rose-950 text-rose-400 border-rose-500/40' : 'bg-emerald-950 text-emerald-400 border-emerald-500/40'} border px-2 py-0.5 rounded-full font-bold">
                        ${isSoldOut ? 'SOLD OUT' : `${evt.available_seats} Seats Available`}
                    </span>
                </div>
                <h3 class="font-bold text-white text-base">${evt.title}</h3>
                <div class="text-xs text-slate-400 space-y-1">
                    <div><i class="fa-solid fa-location-dot mr-1.5 text-slate-500"></i> ${evt.venue_name}</div>
                    <div><i class="fa-solid fa-calendar-day mr-1.5 text-slate-500"></i> ${evt.event_date.replace("T", " ")}</div>
                </div>
                <div class="text-[11px] text-slate-400 pt-1 border-t border-slate-700/60 flex items-center justify-between">
                    <span>${pricesStr}</span>
                    <span class="text-blue-400 font-semibold">Select Seats →</span>
                </div>
            </div>
            `;
        }).join('');

        // Select first event by default if available
        if (events.length > 0 && !currentEvent) {
            selectEvent(events[0].id);
        }

    } catch (e) {
        console.error("Error loading events:", e);
    }
}

function filterEvents(category) {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('bg-blue-600', 'text-white');
        btn.classList.add('bg-slate-800', 'text-slate-300');
    });
    event.target.classList.remove('bg-slate-800', 'text-slate-300');
    event.target.classList.add('bg-blue-600', 'text-white');

    loadEvents(category);
}

// --- Visual Seat Map Renderer & Real-time WebSockets ---
async function selectEvent(eventId) {
    try {
        const res = await fetch(`/api/events/${eventId}`);
        if (!res.ok) return;
        currentEvent = await res.json();

        document.getElementById("noEventSelectedState").classList.add("hidden");
        document.getElementById("activeSeatMapView").classList.remove("hidden");

        document.getElementById("selectedEventTitle").innerText = currentEvent.title;
        document.getElementById("selectedEventMeta").innerText = `${currentEvent.venue_name} (${currentEvent.location}) • Date: ${currentEvent.event_date.replace("T", " ")}`;

        // Render Category Pricing & Waitlist Cards
        const pricingBar = document.getElementById("categoryPricingBar");
        pricingBar.innerHTML = currentEvent.category_stats.map(cs => {
            const isCategorySoldOut = cs.available === 0;
            return `
            <div class="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-center space-y-1">
                <div class="font-bold text-slate-200">${cs.category}</div>
                <div class="text-emerald-400 font-bold text-sm">$${getCategoryPrice(cs.category).toFixed(2)}</div>
                <div class="text-[10px] text-slate-400">${cs.available} / ${cs.total} Left</div>
                ${isCategorySoldOut ? `
                    <button onclick="joinWaitlistPrompt('${currentEvent.id}', '${cs.category}')" class="w-full mt-1 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded font-bold text-[10px]">
                        ⚡ Join Waitlist
                    </button>
                ` : ''}
            </div>
            `;
        }).join('');

        selectedSeatIds = [];
        updateCartUI();

        // Connect WebSocket for real-time updates
        connectWebSocket(eventId);

        // Load Seat Grid
        await loadSeatMap(eventId);

    } catch (e) {
        console.error("Error selecting event:", e);
    }
}

function getCategoryPrice(cat) {
    if (!currentEvent || !currentEvent.prices) return 15.0;
    const p = currentEvent.prices.find(pr => pr.category === cat);
    return p ? p.price : 15.0;
}

async function loadSeatMap(eventId) {
    try {
        const res = await fetch(`/api/seats/event/${eventId}`);
        const data = await res.json();
        currentSeatsMap = data.seats;

        renderSeatGrid();
    } catch (e) {
        console.error("Error loading seat map:", e);
    }
}

function renderSeatGrid() {
    const container = document.getElementById("seatGridContainer");
    if (!currentSeatsMap || currentSeatsMap.length === 0) return;

    // Group seats by row_num
    const rowsMap = {};
    currentSeatsMap.forEach(seat => {
        if (!rowsMap[seat.row_num]) rowsMap[seat.row_num] = [];
        rowsMap[seat.row_num].push(seat);
    });

    container.innerHTML = Object.keys(rowsMap).map(rowNum => {
        const seats = rowsMap[rowNum];
        const rowLabel = seats[0].seat_label.replace(/[0-9]/g, '');

        const seatBtns = seats.map(s => {
            const isSelected = selectedSeatIds.includes(s.id);
            let statusClass = `status-${s.status.toLowerCase()}`;
            if (isSelected) statusClass = "status-selected";

            const catClass = `seat-${s.category.toLowerCase()}`;
            const isMyHold = s.status === 'HELD' && currentUser && s.held_by_user_id === currentUser.id;

            let tooltip = `${s.seat_label} (${s.category}) - $${s.price.toFixed(2)} [Status: ${s.status}]`;
            if (isMyHold) tooltip += " - Held by YOU";

            return `
            <button onclick="toggleSeatSelection('${s.id}')" 
                    title="${tooltip}"
                    ${s.status === 'BOOKED' ? 'disabled' : ''}
                    class="seat-btn w-9 h-9 m-1 rounded-lg font-bold text-xs flex items-center justify-center shadow ${catClass} ${statusClass}">
                ${s.seat_label}
            </button>
            `;
        }).join('');

        return `
        <div class="flex items-center space-x-2">
            <span class="w-6 text-right font-bold text-xs text-slate-500 font-mono">${rowLabel}</span>
            <div class="flex items-center">${seatBtns}</div>
            <span class="w-6 text-left font-bold text-xs text-slate-500 font-mono">${rowLabel}</span>
        </div>
        `;
    }).join('');
}

function toggleSeatSelection(seatId) {
    const seat = currentSeatsMap.find(s => s.id === seatId);
    if (!seat) return;

    if (seat.status === 'BOOKED') {
        showNotification("This seat is already booked.", "warning");
        return;
    }

    if (seat.status === 'HELD' && (!currentUser || seat.held_by_user_id !== currentUser.id)) {
        showNotification("This seat is currently held by another customer.", "warning");
        return;
    }

    const idx = selectedSeatIds.indexOf(seatId);
    if (idx > -1) {
        selectedSeatIds.splice(idx, 1);
    } else {
        selectedSeatIds.push(seatId);
    }

    renderSeatGrid();
    updateCartUI();
}

function updateCartUI() {
    const badges = document.getElementById("selectedSeatsBadges");
    const totalPriceEl = document.getElementById("cartTotalPrice");
    const holdBtn = document.getElementById("holdSeatsBtn");
    const confirmBtn = document.getElementById("confirmBookingBtn");
    const releaseBtn = document.getElementById("releaseSeatsBtn");

    if (selectedSeatIds.length === 0) {
        badges.innerText = "None";
        totalPriceEl.innerText = "$0.00";
        holdBtn.classList.remove("hidden");
        confirmBtn.classList.add("hidden");
        releaseBtn.classList.add("hidden");
        return;
    }

    const selectedSeats = currentSeatsMap.filter(s => selectedSeatIds.includes(s.id));
    const labels = selectedSeats.map(s => s.seat_label);
    const totalPrice = selectedSeats.reduce((acc, s) => acc + s.price, 0);

    badges.innerText = labels.join(", ");
    totalPriceEl.innerText = `$${totalPrice.toFixed(2)}`;

    // Check if seats are already held by current user
    const allHeldByMe = selectedSeats.every(s => s.status === 'HELD' && currentUser && s.held_by_user_id === currentUser.id);

    if (allHeldByMe) {
        holdBtn.classList.add("hidden");
        confirmBtn.classList.remove("hidden");
        releaseBtn.classList.remove("hidden");
    } else {
        holdBtn.classList.remove("hidden");
        confirmBtn.classList.add("hidden");
        releaseBtn.classList.add("hidden");
    }
}

// --- Seat Hold & Concurrency Actions ---
async function holdSelectedSeats() {
    if (!currentUser) {
        openAuthModal();
        return;
    }
    if (selectedSeatIds.length === 0) {
        showNotification("Please select at least one seat first.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/seats/hold", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ event_id: currentEvent.id, seat_ids: selectedSeatIds })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(`Held ${selectedSeatIds.length} seat(s) for 10 minutes!`, "success");
            holdExpirationTime = new Date(data.expires_at).getTime();
            startHoldCountdownTimer();
            await loadSeatMap(currentEvent.id);
            updateCartUI();
        } else {
            showNotification(data.detail || data.message || "Failed to hold seats.", "error");
            await loadSeatMap(currentEvent.id);
        }
    } catch (e) {
        showNotification("Error attempting seat hold.", "error");
    }
}

async function releaseSelectedSeats() {
    if (!currentEvent || selectedSeatIds.length === 0) return;

    try {
        const res = await fetch("/api/seats/release", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ event_id: currentEvent.id, seat_ids: selectedSeatIds })
        });
        if (res.ok) {
            showNotification("Released held seats.", "info");
            stopHoldCountdownTimer();
            selectedSeatIds = [];
            await loadSeatMap(currentEvent.id);
            updateCartUI();
        }
    } catch (e) {
        console.error("Release error:", e);
    }
}

async function confirmSelectedBooking() {
    if (!currentEvent || selectedSeatIds.length === 0) return;

    try {
        const res = await fetch("/api/bookings/confirm", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ event_id: currentEvent.id, seat_ids: selectedSeatIds })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(`🎟️ Booking Confirmed! Ref: ${data.booking_ref}. Ticket QR Sent via Email!`, "success");
            stopHoldCountdownTimer();
            selectedSeatIds = [];
            await loadSeatMap(currentEvent.id);
            updateCartUI();
            switchTab('bookingsTab');
        } else {
            showNotification(data.detail || data.message || "Booking failed.", "error");
        }
    } catch (e) {
        showNotification("Error confirming booking.", "error");
    }
}

// --- Hold Countdown Timer ---
function startHoldCountdownTimer() {
    stopHoldCountdownTimer();
    const container = document.getElementById("holdTimerContainer");
    const textEl = document.getElementById("holdTimerText");
    container.classList.remove("hidden");
    container.classList.add("flex");

    activeHoldTimer = setInterval(() => {
        const now = new Date().getTime();
        const diff = holdExpirationTime - now;

        if (diff <= 0) {
            stopHoldCountdownTimer();
            textEl.innerText = "00:00 EXPIRED";
            showNotification("Your seat hold has expired and seats have been auto-released.", "warning");
            selectedSeatIds = [];
            loadSeatMap(currentEvent.id);
            updateCartUI();
            return;
        }

        const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const secs = Math.floor((diff % (1000 * 60)) / 1000);
        textEl.innerText = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }, 1000);
}

function stopHoldCountdownTimer() {
    if (activeHoldTimer) clearInterval(activeHoldTimer);
    activeHoldTimer = null;
    const container = document.getElementById("holdTimerContainer");
    container.classList.add("hidden");
}

// --- WebSocket Real-Time Listener ---
let reconnectInterval = null;

function connectWebSocket(eventId) {
    if (socket) {
        socket.onclose = null; // Prevent duplicate reconnect triggers on manual switch
        socket.close();
    }
    if (reconnectInterval) clearInterval(reconnectInterval);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/seats/${eventId}`;

    const dot = document.getElementById("wsStatusDot");
    const text = document.getElementById("wsStatusText");

    dot.className = "w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse";
    text.innerText = "Connecting Real-time...";

    try {
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            if (reconnectInterval) clearInterval(reconnectInterval);
            dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-lg";
            text.innerText = "Real-time Live Sync";
        };

        socket.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            console.log("WebSocket event:", msg);

            if (msg.type === "SEAT_HELD" || msg.type === "SEAT_RELEASED" || msg.type === "SEAT_BOOKED") {
                if (currentEvent && msg.event_id === currentEvent.id) {
                    loadSeatMap(currentEvent.id);
                }
            }
        };

        socket.onerror = (err) => {
            console.warn("WebSocket connection error:", err);
        };

        socket.onclose = () => {
            dot.className = "w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse";
            text.innerText = "Reconnecting Sync...";
            
            // Auto-reconnect every 3 seconds if active event is loaded
            if (!reconnectInterval && currentEvent) {
                reconnectInterval = setInterval(() => {
                    if (currentEvent) connectWebSocket(currentEvent.id);
                }, 3000);
            }
        };
    } catch (e) {
        dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        text.innerText = "System Ready";
    }
}

// --- Bookings History & Cancellation ---
async function loadMyBookings() {
    if (!currentUser) return;
    try {
        const res = await fetch("/api/bookings/my", {
            headers: { "Authorization": `Bearer ${currentAuthToken}` }
        });
        const bookings = await res.json();
        const container = document.getElementById("bookingsList");

        if (bookings.length === 0) {
            container.innerHTML = `<div class="col-span-2 p-8 text-center text-slate-500 border border-slate-800 rounded-2xl">No booking history found.</div>`;
            return;
        }

        container.innerHTML = bookings.map(b => {
            const seatsStr = b.seats.map(s => s.seat_label).join(", ");
            const isConfirmed = b.status === "CONFIRMED";

            return `
            <div class="bg-slate-800 border border-slate-700 rounded-2xl p-5 shadow-xl space-y-4">
                <div class="flex items-center justify-between border-b border-slate-700 pb-3">
                    <div>
                        <span class="text-xs font-mono text-slate-400">Ref: ${b.booking_ref}</span>
                        <h3 class="font-bold text-white text-lg">${b.event_title}</h3>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-bold ${isConfirmed ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' : 'bg-slate-900 text-slate-500'}">
                        ${b.status}
                    </span>
                </div>

                <div class="grid grid-cols-2 gap-2 text-xs text-slate-300">
                    <div><span class="text-slate-500">Venue:</span> ${b.venue_name}</div>
                    <div><span class="text-slate-500">Date:</span> ${b.event_date.replace("T", " ")}</div>
                    <div><span class="text-slate-500">Seats:</span> <strong class="text-emerald-400 font-mono">${seatsStr}</strong></div>
                    <div><span class="text-slate-500">Total Paid:</span> <strong class="text-white">${b.total_amount.toFixed(2)}</strong></div>
                </div>

                <!-- QR Ticket Embedded -->
                ${isConfirmed ? `
                <div class="bg-slate-900 p-4 rounded-xl flex items-center justify-between border border-slate-800">
                    <div>
                        <div class="text-xs font-bold text-slate-200">Digital QR Ticket</div>
                        <div class="text-[11px] text-slate-400">Present code at venue entrance</div>
                    </div>
                    <img src="data:image/png;base64,${b.qr_code_data}" alt="QR Ticket" class="w-16 h-16 rounded border border-slate-700 shadow" />
                </div>
                <button onclick="cancelBooking('${b.id}')" class="w-full py-2 bg-rose-950/60 hover:bg-rose-900 text-rose-400 border border-rose-500/30 rounded-lg text-xs font-semibold transition">
                    Cancel Booking & Release Seats to Waitlist
                </button>
                ` : ''}
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Error loading bookings:", e);
    }
}

async function cancelBooking(bookingId) {
    if (!confirm("Are you sure you want to cancel this booking? Released seats will be auto-offered to the next waitlisted customer.")) return;

    try {
        const res = await fetch("/api/bookings/cancel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ booking_id: bookingId })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(`Booking cancelled. Waitlist offers triggered: ${data.waitlist_offers_triggered}`, "success");
            loadMyBookings();
            if (currentEvent) loadSeatMap(currentEvent.id);
        } else {
            showNotification(data.detail || data.message || "Cancellation failed.", "error");
        }
    } catch (e) {
        showNotification("Error cancelling booking.", "error");
    }
}

// --- Waitlist Queue Actions ---
async function joinWaitlistPrompt(eventId, category) {
    if (!currentUser) {
        openAuthModal();
        return;
    }

    try {
        const res = await fetch("/api/waitlist/join", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ event_id: eventId, category: category })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(data.message, "success");
            switchTab('waitlistTab');
        } else {
            showNotification(data.detail || data.message || "Unable to join waitlist.", "error");
        }
    } catch (e) {
        showNotification("Error joining waitlist.", "error");
    }
}

async function loadMyWaitlist() {
    if (!currentUser) return;
    try {
        const res = await fetch("/api/waitlist/my", {
            headers: { "Authorization": `Bearer ${currentAuthToken}` }
        });
        const entries = await res.json();
        const container = document.getElementById("waitlistList");

        if (entries.length === 0) {
            container.innerHTML = `<div class="col-span-2 p-8 text-center text-slate-500 border border-slate-800 rounded-2xl">No waitlist entries.</div>`;
            return;
        }

        container.innerHTML = entries.map(w => {
            const isOffered = w.status === 'OFFERED';

            return `
            <div class="bg-slate-800 border ${isOffered ? 'border-amber-500/80 shadow-amber-500/10' : 'border-slate-700'} rounded-2xl p-5 shadow-xl space-y-4">
                <div class="flex items-center justify-between border-b border-slate-700 pb-3">
                    <div>
                        <h3 class="font-bold text-white text-lg">${w.event_title}</h3>
                        <span class="text-xs text-slate-400">Category: <strong class="text-blue-400">${w.category}</strong></span>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-bold ${isOffered ? 'bg-amber-950 text-amber-400 border border-amber-500 animate-pulse' : 'bg-slate-900 text-slate-400'}">
                        ${w.status}
                    </span>
                </div>

                ${isOffered ? `
                <div class="bg-amber-950/60 border border-amber-500/40 p-4 rounded-xl space-y-2">
                    <div class="text-xs font-bold text-amber-300">⚡ Time-Limited Offer Active!</div>
                    <div class="text-xs text-slate-300">Assigned Seat: <strong class="text-white font-mono">${w.seat_label}</strong></div>
                    <div class="text-xs text-rose-400">Offer Expires: ${w.offer_expires_at.replace("T", " ")} UTC</div>
                    <button onclick="claimWaitlistOffer('${w.id}')" class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg shadow transition">
                        Claim Seat & Confirm Ticket Now
                    </button>
                </div>
                ` : `
                <p class="text-xs text-slate-400">Joined Queue: ${w.created_at.replace("T", " ")}</p>
                `}
            </div>
            `;
        }).join('');
    } catch (e) {
        console.error("Error loading waitlist:", e);
    }
}

async function claimWaitlistOffer(waitlistId) {
    try {
        const res = await fetch("/api/waitlist/claim", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ waitlist_id: waitlistId })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification("🎟️ Waitlist offer claimed and ticket confirmed!", "success");
            switchTab('bookingsTab');
        } else {
            showNotification(data.detail || data.message || "Failed to claim offer.", "error");
        }
    } catch (e) {
        showNotification("Error claiming waitlist offer.", "error");
    }
}

// --- Organiser Dashboard ---
async function loadOrganiserSummary() {
    try {
        const res = await fetch("/api/organiser/summary", {
            headers: { "Authorization": `Bearer ${currentAuthToken}` }
        });
        const data = await res.json();

        document.getElementById("orgRevenueStat").innerText = `$${data.grand_revenue.toFixed(2)}`;
        document.getElementById("orgTicketsStat").innerText = data.total_tickets_sold;
        document.getElementById("orgEventsStat").innerText = data.total_events;

        const tbody = document.getElementById("organiserTableBody");
        tbody.innerHTML = data.events.map(e => `
            <tr class="hover:bg-slate-800/60">
                <td class="p-3.5 font-bold text-white">${e.event_title}</td>
                <td class="p-3.5">${e.venue_name}</td>
                <td class="p-3.5">${e.event_date.replace("T", " ")}</td>
                <td class="p-3.5 text-center">
                    <span class="text-emerald-400 font-bold">${e.available_seats}</span> /
                    <span class="text-amber-400 font-bold">${e.held_seats}</span> /
                    <span class="text-rose-400 font-bold">${e.booked_seats}</span>
                </td>
                <td class="p-3.5 text-right font-bold text-emerald-400">$${e.total_revenue.toFixed(2)}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error("Error loading organiser summary:", e);
    }
}

// --- Admin Venue Creator ---
async function handleCreateVenue(event) {
    event.preventDefault();
    const name = document.getElementById("vName").value;
    const location = document.getElementById("vLoc").value;
    const total_rows = parseInt(document.getElementById("vRows").value);
    const seats_per_row = parseInt(document.getElementById("vSeatsPerRow").value);

    try {
        const res = await fetch("/api/venues", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify({ name, location, total_rows, seats_per_row })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(data.message, "success");
            document.getElementById("createVenueForm").reset();
        } else {
            showNotification(data.detail || "Error creating venue", "error");
        }
    } catch (e) {
        showNotification("Failed to create venue", "error");
    }
}

// --- Create Event Modal ---
async function openCreateEventModal() {
    try {
        const res = await fetch("/api/venues");
        const venues = await res.json();
        const select = document.getElementById("eVenueSelect");

        select.innerHTML = venues.map(v => `<option value="${v.id}">${v.name} (${v.total_rows}x${v.seats_per_row} seats)</option>`).join('');
        document.getElementById("createEventModal").classList.remove("hidden");
    } catch (e) {
        showNotification("Failed to load venues for event creation", "error");
    }
}

function closeCreateEventModal() {
    document.getElementById("createEventModal").classList.add("hidden");
}

async function handleCreateEvent(event) {
    event.preventDefault();
    const title = document.getElementById("eTitle").value;
    const description = document.getElementById("eDesc").value;
    const category = document.getElementById("eCategory").value;
    const venue_id = document.getElementById("eVenueSelect").value;
    const event_date = document.getElementById("eDate").value;

    const pVIP = parseFloat(document.getElementById("pVIP").value);
    const pPREMIUM = parseFloat(document.getElementById("pPREMIUM").value);
    const pSTANDARD = parseFloat(document.getElementById("pSTANDARD").value);

    const payload = {
        title, description, category, venue_id, event_date,
        prices: [
            { category: "VIP", price: pVIP },
            { category: "PREMIUM", price: pPREMIUM },
            { category: "STANDARD", price: pSTANDARD }
        ]
    };

    try {
        const res = await fetch("/api/events", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${currentAuthToken}`
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showNotification(data.message, "success");
            closeCreateEventModal();
            loadEvents();
            loadOrganiserSummary();
        } else {
            showNotification(data.detail || "Failed to publish event", "error");
        }
    } catch (e) {
        showNotification("Error publishing event", "error");
    }
}

// --- Email Inbox Previewer ---
async function loadEmailInbox() {
    try {
        const res = await fetch("/api/emails/inbox");
        const emails = await res.json();
        const container = document.getElementById("emailsList");

        if (emails.length === 0) {
            container.innerHTML = `<div class="p-8 text-center text-slate-500 border border-slate-800 rounded-2xl">No sent emails logged yet.</div>`;
            return;
        }

        container.innerHTML = emails.map(m => `
            <div class="bg-slate-800 border border-slate-700 rounded-2xl p-5 shadow-xl space-y-3">
                <div class="flex items-center justify-between border-b border-slate-700 pb-2 text-xs">
                    <span class="text-slate-400">To: <strong class="text-white">${m.to_email}</strong></span>
                    <span class="text-slate-500 font-mono">${m.created_at.replace("T", " ").substring(0, 19)}</span>
                </div>
                <h4 class="font-bold text-white text-sm">${m.subject}</h4>
                <div class="bg-white text-slate-900 p-4 rounded-xl font-sans text-xs">
                    ${m.body_html}
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error loading email inbox:", e);
    }
}

// --- Auth Modal & Handlers ---
let authMode = "LOGIN";

function openAuthModal() {
    document.getElementById("authModal").classList.remove("hidden");
}

function closeAuthModal() {
    document.getElementById("authModal").classList.add("hidden");
}

function toggleAuthMode() {
    authMode = authMode === "LOGIN" ? "REGISTER" : "LOGIN";
    const title = document.getElementById("authModalTitle");
    const nameField = document.getElementById("nameField");
    const roleField = document.getElementById("roleField");
    const submitBtn = document.getElementById("authSubmitBtn");
    const toggleBtn = document.getElementById("authToggleBtn");

    if (authMode === "REGISTER") {
        title.innerText = "Create New Account";
        nameField.classList.remove("hidden");
        roleField.classList.remove("hidden");
        submitBtn.innerText = "Register Account";
        toggleBtn.innerText = "Already have an account? Sign in";
    } else {
        title.innerText = "Sign In to EventMaster";
        nameField.classList.add("hidden");
        roleField.classList.add("hidden");
        submitBtn.innerText = "Sign In";
        toggleBtn.innerText = "Don't have an account? Register here";
    }
}

async function handleAuthSubmit(event) {
    event.preventDefault();
    const email = document.getElementById("authEmail").value;
    const password = document.getElementById("authPassword").value;

    if (authMode === "LOGIN") {
        await quickLogin(email, password);
        closeAuthModal();
    } else {
        const name = document.getElementById("authName").value;
        const role = document.getElementById("authRole").value;

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password, name, role })
            });
            const data = await res.json();
            if (res.ok) {
                currentAuthToken = data.access_token;
                localStorage.setItem("token", currentAuthToken);
                currentUser = { id: data.user_id, email: data.email, name: data.name, role: data.role };
                updateAuthUI();
                showNotification(`Account created! Logged in as ${data.name}`, "success");
                closeAuthModal();
            } else {
                showNotification(data.detail || "Registration failed", "error");
            }
        } catch (e) {
            showNotification("Registration error", "error");
        }
    }
}

// --- Notification Banner ---
function showNotification(msg, type = "info") {
    const banner = document.getElementById("systemNotification");
    const text = document.getElementById("notifMessage");
    const icon = document.getElementById("notifIcon");

    text.innerText = msg;
    banner.classList.remove("hidden");

    if (type === "success") {
        icon.className = "fa-solid fa-circle-check text-emerald-400 text-lg";
    } else if (type === "error") {
        icon.className = "fa-solid fa-circle-xmark text-rose-400 text-lg";
    } else if (type === "warning") {
        icon.className = "fa-solid fa-triangle-exclamation text-amber-400 text-lg";
    } else {
        icon.className = "fa-solid fa-circle-info text-blue-400 text-lg";
    }

    setTimeout(() => { dismissNotification(); }, 6000);
}

function dismissNotification() {
    document.getElementById("systemNotification").classList.add("hidden");
}
