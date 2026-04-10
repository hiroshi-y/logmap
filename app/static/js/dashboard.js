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

// Incrementing z-index counter so the last-clicked card is always on top
let nextZIndex = 900;


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
    // Remove all dot entries (keep mini-panels for ongoing session if any)
    const dotsToRemove = qsoEntries.filter(e => e.isDot);
    dotsToRemove.forEach(entry => {
        entry.marker.setMap(null);
        if (entry.infoWindow) entry.infoWindow.close();
    });
    // Remove dots from array
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

    // Initialize SocketIO after map is ready
    initSocketIO();

    // Start clock
    updateClock();
    setInterval(updateClock, 1000);
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
        // Clear existing
        clearAllMarkers();
        // Add all QSOs
        qsos.forEach((qso, index) => {
            const isLatest = (index === qsos.length - 1);
            addQsoToMap(qso, isLatest);
        });
        resetZoom();
        setStatus('status.monitoring');
    });

    socket.on('new_qso', (qso) => {
        // Shrink previous active mini-panel
        shrinkActivePanels();
        // Add new QSO
        addQsoToMap(qso, true);
        // Manage overflow
        enforceMaxPanels();
        // Update zoom
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
    // Check if another QSO already exists at (nearly) the same location
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

    // Active card always gets the highest z-index
    const zIdx = isActive ? ++nextZIndex : 500;

    // Create marker
    const marker = new google.maps.Marker({
        position: position,
        map: map,
        icon: getMarkerIcon(isActive),
        zIndex: zIdx,
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

    // Store entry (must be created before opening InfoWindow)
    const entry = {
        marker: marker,
        infoWindow: infoWindow,
        qso: qso,
        isDot: false,
        isActive: isActive,
        _infoOpen: isActive,
        _panelId: panelIdCounter,  // matches data-panel-id in the HTML
        _iwContainer: null,        // cached DOM ref, set on first domready
    };
    qsoEntries.push(entry);

    if (isActive) {
        infoWindow.open(map, marker);
        bringInfoWindowToFront(entry);
    }

    // Click to toggle info window (for dots: restore card, re-click: back to dot)
    marker.addListener('click', () => {
        if (entry._infoOpen) {
            // Close the card; if it was a dot, return to dot appearance
            infoWindow.close();
            entry._infoOpen = false;
            if (entry.isDot) {
                marker.setIcon(getDotIcon());
                marker.setZIndex(100);
            }
        } else {
            // Show the card; if it's a dot, temporarily show full card
            if (entry.isDot) {
                const content = createMiniPanelHtml(entry.qso, false);
                infoWindow.setContent(content);
                marker.setIcon(getMarkerIcon(false));
                entry._iwContainer = null;  // content changed, recapture
            }
            infoWindow.open(map, marker);
            bringInfoWindowToFront(entry);
            entry._infoOpen = true;
        }
    });
}

let panelIdCounter = 0;

function createMiniPanelHtml(qso, isActive) {
    const sizeClass = isActive ? 'active' : 'past';
    const distStr = qso.distance_km.toLocaleString(undefined, { maximumFractionDigits: 0 });
    const panelId = `mp-${++panelIdCounter}`;

    return `
        <div class="mini-panel ${sizeClass}" data-panel-id="${panelId}">
            <div class="mp-callsign">${escapeHtml(qso.callsign)}</div>
            <div class="mp-location">${escapeHtml(qso.city_name)}</div>
            <div class="mp-info">
                <span class="mp-distance">${distStr} km</span>
                <span class="mp-band">${escapeHtml(qso.band)} ${escapeHtml(qso.mode)}</span>
            </div>
        </div>
    `;
}

function captureInfoWindowContainer(entry) {
    // On domready, walk up from the mini-panel to find the InfoWindow's
    // outermost absolutely-positioned container and cache it on the entry.
    google.maps.event.addListenerOnce(entry.infoWindow, 'domready', () => {
        const panelId = entry._panelId;
        const panel = document.querySelector(`.mini-panel[data-panel-id="${panelId}"]`);
        if (!panel) return;
        let node = panel;
        while (node && node.parentElement) {
            node = node.parentElement;
            if (node.style && node.style.position === 'absolute'
                && node.parentElement && node.parentElement.style
                && node.parentElement.style.position === 'absolute') {
                entry._iwContainer = node;
                node.style.zIndex = String(++nextZIndex);
                break;
            }
        }
    });
}

function bringInfoWindowToFront(entry) {
    if (entry._iwContainer) {
        entry._iwContainer.style.zIndex = String(++nextZIndex);
    } else {
        // First time — capture the container reference
        captureInfoWindowContainer(entry);
    }
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
            // Update marker icon to smaller
            entry.marker.setIcon(getMarkerIcon(false));
            entry.marker.setZIndex(500);
            // Update info window content to past style
            const pastContent = createMiniPanelHtml(entry.qso, false);
            entry.infoWindow.setContent(pastContent);
        }
    });
}

function enforceMaxPanels() {
    // Count non-dot entries
    const panelEntries = qsoEntries.filter(e => !e.isDot);
    const excess = panelEntries.length - MAX_MINI_PANELS;

    if (excess > 0) {
        // Convert oldest panels to dots
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
    // Always include station
    bounds.extend({
        lat: LOGMAP_CONFIG.stationLat,
        lng: LOGMAP_CONFIG.stationLon,
    });

    // Include all visible markers
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
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = getTranslation(key);
    });
    // Update title attributes
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        el.title = getTranslation(key);
    });
    // Update page title
    document.title = getTranslation('app_title');
}

// Language switcher
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const lang = btn.getAttribute('data-lang');
            // Update active state
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            // Notify server
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
