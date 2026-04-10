/**
 * LogMap Dashboard - Client-side JavaScript
 *
 * Manages Google Map, real-time QSO display with mini-panels,
 * statistics, clock, and SocketIO communication.
 */

/* ===== Global State ===== */
let map;
let socket;
let translations = LOGMAP_CONFIG.translations;
let stationMarker;

// QSO markers and info windows
const qsoEntries = [];      // Array of { marker, infoWindow, qso, isDot }
const MAX_MINI_PANELS = LOGMAP_CONFIG.maxMiniPanels;

// Track today's date for midnight rollover
let todayDateStr = new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD


/* ===== Clock ===== */
function updateClock() {
    const now = new Date();

    // Local time
    const localStr = now.toLocaleTimeString('ja-JP', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    });
    document.getElementById('clock-local-time').textContent = localStr;

    // UTC
    const utcStr = now.toLocaleTimeString('ja-JP', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        hour12: false, timeZone: 'UTC'
    });
    document.getElementById('clock-utc-time').textContent = utcStr;

    // Check midnight rollover
    const currentDate = now.toLocaleDateString('en-CA');
    if (currentDate !== todayDateStr) {
        todayDateStr = currentDate;
        handleMidnightRollover();
    }
}

function handleMidnightRollover() {
    const dotsToRemove = qsoEntries.filter(e => e.isDot);
    dotsToRemove.forEach(entry => {
        entry.marker.setMap(null);
        if (entry.infoWindow) entry.infoWindow.close();
    });
    for (let i = qsoEntries.length - 1; i >= 0; i--) {
        if (qsoEntries[i].isDot) {
            qsoEntries.splice(i, 1);
        }
    }
}


/* ===== Google Map Initialization ===== */
function initMap() {
    if (window._mapInitialized) return;
    window._mapInitialized = true;

    const stationPos = {
        lat: LOGMAP_CONFIG.stationLat,
        lng: LOGMAP_CONFIG.stationLon
    };

    map = new google.maps.Map(document.getElementById('map'), {
        center: stationPos,
        zoom: 6,
        mapTypeId: 'roadmap',
        styles: getMapDarkStyle(),
        disableDefaultUI: true,
        zoomControl: false,
        gestureHandling: 'greedy',
    });

    // Station marker (home position)
    stationMarker = new google.maps.Marker({
        position: stationPos,
        map: map,
        title: LOGMAP_CONFIG.stationCall,
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: '#ff4444',
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 3,
        },
        zIndex: 1000,
    });

    // Station label
    new google.maps.InfoWindow({
        content: `<div style="background:#1a1a2e;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;font-size:14px;">${LOGMAP_CONFIG.stationCall}</div>`,
        disableAutoPan: true,
    }).open(map, stationMarker);

    // Map controls
    document.getElementById('btn-zoom-in').addEventListener('click', () => {
        map.setZoom(map.getZoom() + 1);
    });
    document.getElementById('btn-zoom-out').addEventListener('click', () => {
        map.setZoom(map.getZoom() - 1);
    });
    document.getElementById('btn-reset-zoom').addEventListener('click', resetZoom);

    // ---- DEBUG: two test pins with z-order display ----
    addDebugPins();

    // Initialize SocketIO after map is ready
    initSocketIO();

    // Start clock
    updateClock();
    setInterval(updateClock, 1000);
}


/* ===== InfoWindow z-order control ===== */
// Google Maps InfoWindow DOM structure (confirmed via debug):
//   L5: .gm-style-iw-a  (position: absolute)
//   L6: div              (position: absolute, zIndex: -29 etc.) <-- THIS controls stacking
//   L7: div              (position: absolute, zIndex: 107)      <-- shared pane for all IWs
//
// To bring an InfoWindow to front, set L6's zIndex to a high value.
// L6 = .gm-style-iw-a's parentElement.

let nextIwZIndex = 10000;

function getIwContainer(infoWindow) {
    // Find .gm-style-iw-a that belongs to this InfoWindow by searching
    // all such elements for one that contains the InfoWindow's content.
    const candidates = document.querySelectorAll('.gm-style-iw-a');
    // The last one added is most likely ours, but we search to be safe
    for (const el of candidates) {
        // L6 is el.parentElement
        if (el.parentElement) return el.parentElement;
    }
    return null;
}

function cacheIwContainer(entry) {
    // Called on domready: find and cache this entry's L6 container.
    // We identify it by looking for the one with matching content text.
    const callsign = entry.qso ? entry.qso.callsign : '';
    const candidates = document.querySelectorAll('.gm-style-iw-a');
    for (const el of candidates) {
        if (callsign && el.textContent.includes(callsign)) {
            entry._iwL6 = el.parentElement;
            return;
        }
    }
}

function bringToFront(entry) {
    if (entry._iwL6) {
        entry._iwL6.style.zIndex = String(++nextIwZIndex);
    }
}


/* ===== Debug Pins ===== */
function addDebugPins() {
    const pins = [
        { id: 'dbgA', label: 'A', color: '#ff00ff', dLat: 0.15, dLng: 0.15 },
        { id: 'dbgB', label: 'B', color: '#00ffff', dLat: 0.17, dLng: 0.17 },
    ];
    pins.forEach(p => {
        const pos = {
            lat: LOGMAP_CONFIG.stationLat + p.dLat,
            lng: LOGMAP_CONFIG.stationLon + p.dLng,
        };
        const marker = new google.maps.Marker({
            position: pos, map: map,
            icon: { path: google.maps.SymbolPath.CIRCLE, scale: 10,
                    fillColor: p.color, fillOpacity: 1, strokeColor: '#fff', strokeWeight: 3 },
            zIndex: 500,
        });
        const iw = new google.maps.InfoWindow({ disableAutoPan: true });
        let iwL6 = null;

        function updateContent() {
            const z = iwL6 ? iwL6.style.zIndex : '(not cached)';
            iw.setContent(
                `<div id="${p.id}" style="background:${p.color};color:#fff;padding:12px;border-radius:6px;font-size:16px;cursor:pointer;min-width:150px;">` +
                `<b>デバッグ ${p.label}</b><br>` +
                `L6 z-index: <b>${z}</b><br>` +
                `<small>カードをクリック → z-order UP</small></div>`
            );
        }

        google.maps.event.addListener(iw, 'domready', () => {
            // Cache L6: walk up from .gm-style-iw-a
            if (!iwL6) {
                const all = document.querySelectorAll('.gm-style-iw-a');
                for (const el of all) {
                    if (el.textContent.includes('デバッグ ' + p.label)) {
                        iwL6 = el.parentElement;
                        break;
                    }
                }
            }
            updateContent();

            // Attach click on the card content
            const el = document.getElementById(p.id);
            if (el) {
                el.onclick = () => {
                    if (iwL6) {
                        iwL6.style.zIndex = String(++nextIwZIndex);
                        console.log(`${p.label}: set L6 zIndex to ${nextIwZIndex}`);
                    } else {
                        console.log(`${p.label}: iwL6 is null!`);
                    }
                    // Refresh display after a tick
                    setTimeout(updateContent, 50);
                };
            }
        });

        // Open on pin click (pin is visible because no IW covers it initially)
        marker.addListener('click', () => {
            iw.open(map, marker);
        });
        // Auto-open
        iw.open(map, marker);
    });
}


/* ===== Map Dark Style ===== */
function getMapDarkStyle() {
    return [
        { elementType: 'geometry', stylers: [{ color: '#1d2c4d' }] },
        { elementType: 'labels.text.fill', stylers: [{ color: '#8ec3b9' }] },
        { elementType: 'labels.text.stroke', stylers: [{ color: '#1a3646' }] },
        { featureType: 'administrative.country', elementType: 'geometry.stroke', stylers: [{ color: '#4b6878' }] },
        { featureType: 'administrative.province', elementType: 'geometry.stroke', stylers: [{ color: '#4b6878' }] },
        { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0e1626' }] },
        { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#4e6d70' }] },
        { featureType: 'road', stylers: [{ visibility: 'off' }] },
        { featureType: 'transit', stylers: [{ visibility: 'off' }] },
        { featureType: 'poi', stylers: [{ visibility: 'off' }] },
        { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#1a2744' }] },
    ];
}


/* ===== SocketIO ===== */
function initSocketIO() {
    socket = io();

    socket.on('connect', () => {
        setStatus('status.connected');
    });

    socket.on('disconnect', () => {
        setStatus('status.disconnected');
    });

    socket.on('initial_qsos', (qsos) => {
        clearAllMarkers();
        qsos.forEach((qso, index) => {
            const isLatest = (index === qsos.length - 1);
            addQsoToMap(qso, isLatest);
        });
        resetZoom();
        setStatus('status.monitoring');
    });

    socket.on('new_qso', (qso) => {
        shrinkActivePanels();
        addQsoToMap(qso, true);
        enforceMaxPanels();
        resetZoom();
    });

    socket.on('stats_update', (stats) => {
        updateStats(stats);
    });

    socket.on('language_changed', (data) => {
        translations = data.translations;
        applyTranslations();
    });
}


/* ===== QSO Map Management ===== */
function jitterPosition(lat, lng) {
    const threshold = 0.002; // ~200m
    const overlap = qsoEntries.some(e => {
        const pos = e.marker.getPosition();
        return Math.abs(pos.lat() - lat) < threshold
            && Math.abs(pos.lng() - lng) < threshold;
    });
    if (!overlap) return { lat, lng };
    // Random offset 0.01–0.02 deg (~1–2km) in a random direction
    const angle = Math.random() * 2 * Math.PI;
    const dist = 0.01 + Math.random() * 0.01;
    return { lat: lat + dist * Math.sin(angle), lng: lng + dist * Math.cos(angle) };
}

function addQsoToMap(qso, isActive) {
    const position = jitterPosition(qso.latitude, qso.longitude);

    // Create marker
    const marker = new google.maps.Marker({
        position: position,
        map: map,
        icon: getMarkerIcon(isActive),
        zIndex: isActive ? 999 : 500,
    });

    if (isActive) {
        marker.setAnimation(google.maps.Animation.DROP);
    }

    // Create info window with mini-panel content
    const content = createMiniPanelHtml(qso, isActive);
    const infoWindow = new google.maps.InfoWindow({
        content: content,
        disableAutoPan: true,
        pixelOffset: new google.maps.Size(0, -5),
    });

    // Store entry
    const entry = {
        marker: marker,
        infoWindow: infoWindow,
        qso: qso,
        isDot: false,
        isActive: isActive,
        _infoOpen: isActive,
        _iwL6: null,  // cached DOM ref to the L6 container for z-order
    };
    qsoEntries.push(entry);

    if (isActive) {
        infoWindow.open(map, marker);
    }

    // On domready, cache the L6 container, bring active to front,
    // and add click handler on the card to bring it to front
    google.maps.event.addListener(infoWindow, 'domready', () => {
        if (!entry._iwL6) {
            cacheIwContainer(entry);
        }
        if (entry.isActive) {
            bringToFront(entry);
        }
        // Attach click-to-front on the card content itself
        // (marker click doesn't fire when InfoWindow covers it)
        const iwA = entry._iwL6 ? entry._iwL6.querySelector('.gm-style-iw-a') : null;
        if (iwA) {
            iwA.onclick = () => bringToFront(entry);
        }
    });

    // Click to toggle info window
    marker.addListener('click', () => {
        if (entry._infoOpen) {
            infoWindow.close();
            entry._infoOpen = false;
            if (entry.isDot) {
                marker.setIcon(getDotIcon());
                marker.setZIndex(100);
            }
        } else {
            if (entry.isDot) {
                infoWindow.setContent(createMiniPanelHtml(entry.qso, false));
                marker.setIcon(getMarkerIcon(false));
                entry._iwL6 = null;  // content changed, need to recache
            }
            infoWindow.open(map, marker);
            entry._infoOpen = true;
            // bringToFront will be called on domready
        }
    });
}

function createMiniPanelHtml(qso, isActive) {
    const sizeClass = isActive ? 'active' : 'past';
    const distStr = qso.distance_km.toLocaleString(undefined, { maximumFractionDigits: 0 });

    return `
        <div class="mini-panel ${sizeClass}">
            <div class="mp-callsign">${escapeHtml(qso.callsign)}</div>
            <div class="mp-location">${escapeHtml(qso.city_name)}</div>
            <div class="mp-info">
                <span class="mp-distance">${distStr} km</span>
                <span class="mp-band">${escapeHtml(qso.band)} ${escapeHtml(qso.mode)}</span>
            </div>
        </div>
    `;
}

function getMarkerIcon(isActive) {
    if (isActive) {
        return {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: '#00e676',
            fillOpacity: 1,
            strokeColor: '#ffffff',
            strokeWeight: 2,
        };
    }
    return {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 6,
        fillColor: '#ffc107',
        fillOpacity: 0.9,
        strokeColor: '#ffffff',
        strokeWeight: 1,
    };
}

function getDotIcon() {
    return {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 3,
        fillColor: '#888888',
        fillOpacity: 0.6,
        strokeColor: '#aaaaaa',
        strokeWeight: 1,
    };
}

function shrinkActivePanels() {
    qsoEntries.forEach(entry => {
        if (entry.isActive && !entry.isDot) {
            entry.isActive = false;
            entry.marker.setIcon(getMarkerIcon(false));
            entry.marker.setZIndex(500);
            entry.infoWindow.setContent(createMiniPanelHtml(entry.qso, false));
        }
    });
}

function enforceMaxPanels() {
    const panelEntries = qsoEntries.filter(e => !e.isDot);
    const excess = panelEntries.length - MAX_MINI_PANELS;

    if (excess > 0) {
        for (let i = 0; i < excess; i++) {
            const entry = panelEntries[i];
            entry.isDot = true;
            entry.isActive = false;
            entry._infoOpen = false;
            entry.infoWindow.close();
            entry.marker.setIcon(getDotIcon());
            entry.marker.setZIndex(100);
        }
    }
}

function clearAllMarkers() {
    qsoEntries.forEach(entry => {
        entry.marker.setMap(null);
        entry.infoWindow.close();
    });
    qsoEntries.length = 0;
}


/* ===== Zoom Management ===== */
function resetZoom() {
    if (!map) return;

    const bounds = new google.maps.LatLngBounds();
    bounds.extend({
        lat: LOGMAP_CONFIG.stationLat,
        lng: LOGMAP_CONFIG.stationLon,
    });

    qsoEntries.forEach(entry => {
        bounds.extend(entry.marker.getPosition());
    });

    if (qsoEntries.length > 0) {
        map.fitBounds(bounds, { top: 60, bottom: 60, left: 40, right: 60 });
    } else {
        map.setCenter({
            lat: LOGMAP_CONFIG.stationLat,
            lng: LOGMAP_CONFIG.stationLon,
        });
        map.setZoom(6);
    }
}


/* ===== Statistics ===== */
function updateStats(stats) {
    document.getElementById('stats-total').textContent = stats.total_qsos || 0;
    document.getElementById('stats-farthest-call').textContent = stats.farthest_call || '-';
    document.getElementById('stats-farthest-location').textContent = stats.farthest_location || '-';

    const dist = stats.farthest_distance || 0;
    const distStr = dist > 0
        ? `${dist.toLocaleString(undefined, { maximumFractionDigits: 0 })} km`
        : '- km';
    document.getElementById('stats-farthest-distance').textContent = distStr;
}


/* ===== i18n ===== */
function setStatus(key) {
    const el = document.getElementById('status-text');
    el.textContent = getTranslation(key);
}

function getTranslation(key) {
    const parts = key.split('.');
    let value = translations;
    for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
            value = value[part];
        } else {
            return key;
        }
    }
    return typeof value === 'string' ? value : key;
}

function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = getTranslation(key);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        el.title = getTranslation(key);
    });
    document.title = getTranslation('app_title');
}

// Language switcher
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const lang = btn.getAttribute('data-lang');
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (socket && socket.connected) {
                socket.emit('change_language', { lang: lang });
            }
        });
    });
});


/* ===== Utility ===== */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
