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
    updateFarthestLines();
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

    // Initialize SocketIO after map is ready
    initSocketIO();

    // Start clock
    updateClock();
    setInterval(updateClock, 1000);
}


/* ===== InfoWindow z-order control ===== */
// Google Maps InfoWindow DOM structure (confirmed via debug):
//   L5: .gm-style-iw-a  (position: absolute)
//   L6: div              (position: absolute, zIndex controls stacking)
//   L7: div              (position: absolute, zIndex: 107, shared pane)
// To bring an InfoWindow to front, set L6's zIndex to a high value.
// L6 = .gm-style-iw-a.parentElement

let nextIwZIndex = 10000;

// Number of InfoWindows waiting for domready to fire
let _pendingDomready = 0;

function bringToFront(entry) {
    if (entry._iwL6) {
        entry._iwL6.style.zIndex = String(++nextIwZIndex);
    }
    // Active (yellow) card always stays on top
    if (!entry.isActive) {
        const active = qsoEntries.find(e => e.isActive && e._iwL6);
        if (active) {
            active._iwL6.style.zIndex = String(++nextIwZIndex);
        }
    }
}


/* ===== Great Circle Lines to Top-3 Farthest ===== */
const farthestLines = [];  // Array of google.maps.Polyline
const FARTHEST_COLORS = ['#ff4444', '#ff8800', '#ffcc00']; // 1st, 2nd, 3rd

function updateFarthestLines() {
    // Remove old lines
    farthestLines.forEach(line => line.setMap(null));
    farthestLines.length = 0;

    if (!map) return;

    const stationPos = { lat: LOGMAP_CONFIG.stationLat, lng: LOGMAP_CONFIG.stationLon };

    // Top 3 farthest QSOs by distance
    const sorted = qsoEntries
        .filter(e => e.qso.distance_km > 0)
        .sort((a, b) => b.qso.distance_km - a.qso.distance_km)
        .slice(0, 3);

    sorted.forEach((entry, i) => {
        const line = new google.maps.Polyline({
            path: [stationPos, entry.marker.getPosition()],
            geodesic: true,
            strokeColor: FARTHEST_COLORS[i],
            strokeOpacity: 0.7,
            strokeWeight: i === 0 ? 3 : 2,
            map: map,
            zIndex: 10,
        });
        farthestLines.push(line);
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
        const openCount = LOGMAP_CONFIG.openCards || 1;
        const openStart = Math.max(0, qsos.length - openCount);
        // Count how many cards will open (need domready before raising active)
        _pendingDomready = qsos.filter((_, i) => i >= openStart).length;
        qsos.forEach((qso, index) => {
            const isLatest = (index === qsos.length - 1);
            const showCard = (index >= openStart);
            addQsoToMap(qso, isLatest, showCard);
        });
        updateFarthestLines();
        resetZoom();
        setStatus('status.monitoring');
    });

    socket.on('new_qso', (qso) => {
        shrinkActivePanels();
        _pendingDomready = 1;
        addQsoToMap(qso, true);
        enforceMaxPanels();
        updateFarthestLines();
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

let panelIdCounter = 0;

function addQsoToMap(qso, isActive, showCard) {
    // showCard: whether to open the InfoWindow (defaults to isActive)
    if (showCard === undefined) showCard = isActive;

    const position = jitterPosition(qso.latitude, qso.longitude);
    const panelId = 'qso-panel-' + (++panelIdCounter);

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
    const content = createMiniPanelHtml(qso, isActive, panelId);
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
        _infoOpen: showCard,
        _panelId: panelId,
        _iwL6: null,
    };
    qsoEntries.push(entry);

    if (showCard) {
        infoWindow.open(map, marker);
    }

    // On domready: cache L6, attach click handler.
    // When the last pending card is ready, "click" the active card to raise it.
    google.maps.event.addListener(infoWindow, 'domready', () => {
        const panelEl = document.getElementById(entry._panelId);
        if (panelEl) {
            let el = panelEl;
            while (el && !el.classList.contains('gm-style-iw-a')) {
                el = el.parentElement;
            }
            if (el && el.parentElement) {
                entry._iwL6 = el.parentElement;
            }
            panelEl.style.cursor = 'pointer';
            panelEl.onclick = () => bringToFront(entry);
        }
        // After the last card renders, raise active on the next event loop
        // tick (same timing as a real user click — Google Maps may still
        // adjust z-index within the current domready cycle).
        if (_pendingDomready > 0) {
            _pendingDomready--;
            if (_pendingDomready === 0) {
                setTimeout(() => {
                    // Simulate clicking a blue card: this sets the blue
                    // card's z-index (overriding Google's value) AND then
                    // raises the active card above it.
                    const anyPast = qsoEntries.find(e => !e.isActive && e._iwL6 && e._infoOpen);
                    if (anyPast) {
                        bringToFront(anyPast);
                    } else {
                        const active = qsoEntries.find(e => e.isActive && e._iwL6);
                        if (active) bringToFront(active);
                    }
                }, 0);
            }
        }
    });

    // Click marker to toggle info window
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
                infoWindow.setContent(createMiniPanelHtml(entry.qso, false, entry._panelId));
                marker.setIcon(getMarkerIcon(false));
            }
            infoWindow.open(map, marker);
            entry._infoOpen = true;
        }
    });
}

function createMiniPanelHtml(qso, isActive, panelId) {
    const sizeClass = isActive ? 'active' : 'past';
    const distStr = qso.distance_km.toLocaleString(undefined, { maximumFractionDigits: 0 });

    return `
        <div id="${panelId}" class="mini-panel ${sizeClass}">
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
            entry.infoWindow.setContent(createMiniPanelHtml(entry.qso, false, entry._panelId));
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
    farthestLines.forEach(line => line.setMap(null));
    farthestLines.length = 0;
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
