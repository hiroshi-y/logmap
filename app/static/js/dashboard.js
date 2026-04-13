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

const qsoEntries = [];
const MAX_OPEN_CARDS = LOGMAP_CONFIG.openCards || 1;

let todayDateStr = new Date().toLocaleDateString('en-CA');


/* ===== Clock ===== */
function updateClock() {
    const now = new Date();

    document.getElementById('clock-local-time').textContent =
        now.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

    document.getElementById('clock-utc-time').textContent =
        now.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'UTC' });

    const currentDate = now.toLocaleDateString('en-CA');
    if (currentDate !== todayDateStr) {
        todayDateStr = currentDate;
        handleMidnightRollover();
    }
}

function handleMidnightRollover() {
    for (let i = qsoEntries.length - 1; i >= 0; i--) {
        if (qsoEntries[i].isDot) {
            qsoEntries[i].marker.setMap(null);
            qsoEntries[i].infoWindow.close();
            qsoEntries.splice(i, 1);
        }
    }
    updateFarthestLines();
}


/* ===== Google Map Initialization ===== */
function initMap() {
    if (window._mapInitialized) return;
    window._mapInitialized = true;

    const stationPos = { lat: LOGMAP_CONFIG.stationLat, lng: LOGMAP_CONFIG.stationLon };

    map = new google.maps.Map(document.getElementById('map'), {
        center: stationPos,
        zoom: 6,
        mapTypeId: 'roadmap',
        styles: getMapDarkStyle(),
        disableDefaultUI: true,
        zoomControl: false,
        gestureHandling: 'greedy',
    });

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

    new google.maps.InfoWindow({
        content: `<div style="background:#1a1a2e;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;font-size:14px;">${LOGMAP_CONFIG.stationCall}</div>`,
        disableAutoPan: true,
    }).open(map, stationMarker);

    document.getElementById('btn-zoom-in').addEventListener('click', () => map.setZoom(map.getZoom() + 1));
    document.getElementById('btn-zoom-out').addEventListener('click', () => map.setZoom(map.getZoom() - 1));
    document.getElementById('btn-reset-zoom').addEventListener('click', resetZoom);

    initSocketIO();
    updateClock();
    setInterval(updateClock, 1000);
}


/* ===== InfoWindow z-order ===== */
// Google Maps reassigns L6 z-index on every render cycle (open, drag, zoom).
// A MutationObserver per card enforces our desired z-index.

const ACTIVE_ZINDEX = 99999;
let nextIwZIndex = 10000;

function setZIndexGuard(entry, zIndex) {
    if (!entry._iwL6) return;
    entry._guardedZ = zIndex;
    entry._iwL6.style.zIndex = String(zIndex);
    if (entry._zObserver) return;
    entry._zObserver = new MutationObserver(() => {
        if (entry._guardedZ != null && parseInt(entry._iwL6.style.zIndex) !== entry._guardedZ) {
            entry._iwL6.style.zIndex = String(entry._guardedZ);
        }
    });
    entry._zObserver.observe(entry._iwL6, { attributes: true, attributeFilter: ['style'] });
}

function clearZIndexGuard(entry) {
    if (entry._zObserver) {
        entry._zObserver.disconnect();
        entry._zObserver = null;
    }
    entry._guardedZ = null;
}

function bringToFront(entry) {
    nextIwZIndex = Math.max(nextIwZIndex, ACTIVE_ZINDEX) + 1;
    setZIndexGuard(entry, nextIwZIndex);
}


/* ===== Great Circle Lines to Top-3 Farthest ===== */
const farthestLines = [];
const FARTHEST_COLORS = ['#ff4444', '#ff8800', '#ffcc00'];

function updateFarthestLines() {
    farthestLines.forEach(line => line.setMap(null));
    farthestLines.length = 0;
    if (!map) return;

    const stationPos = { lat: LOGMAP_CONFIG.stationLat, lng: LOGMAP_CONFIG.stationLon };
    const top3 = qsoEntries
        .filter(e => e.qso.distance_km > 0)
        .sort((a, b) => b.qso.distance_km - a.qso.distance_km)
        .slice(0, 3);

    top3.forEach((entry, i) => {
        farthestLines.push(new google.maps.Polyline({
            path: [stationPos, entry.marker.getPosition()],
            geodesic: true,
            strokeColor: FARTHEST_COLORS[i],
            strokeOpacity: 0.7,
            strokeWeight: i === 0 ? 3 : 2,
            map: map,
            zIndex: 10,
        }));
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
    socket = io({
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 30000,
    });

    socket.on('connect', () => setStatus('status.connected'));
    socket.on('disconnect', () => setStatus('status.disconnected'));

    socket.on('initial_qsos', (qsos) => {
        clearAllMarkers();
        const openCount = LOGMAP_CONFIG.openCards || 1;
        const openStart = Math.max(0, qsos.length - openCount);
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
        addQsoToMap(qso, true);
        enforceMaxPanels();
        updateFarthestLines();
        resetZoom();
    });

    socket.on('stats_update', updateStats);

    socket.on('language_changed', (data) => {
        translations = data.translations;
        applyTranslations();
    });
}


/* ===== QSO Map Management ===== */
function jitterPosition(lat, lng) {
    const threshold = 0.002;
    const overlap = qsoEntries.some(e => {
        const pos = e.marker.getPosition();
        return Math.abs(pos.lat() - lat) < threshold
            && Math.abs(pos.lng() - lng) < threshold;
    });
    if (!overlap) return { lat, lng };
    const angle = Math.random() * 2 * Math.PI;
    const dist = 0.01 + Math.random() * 0.01;
    return { lat: lat + dist * Math.sin(angle), lng: lng + dist * Math.cos(angle) };
}

let panelIdCounter = 0;

function addQsoToMap(qso, isActive, showCard) {
    if (showCard === undefined) showCard = isActive;

    const position = jitterPosition(qso.latitude, qso.longitude);
    const panelId = 'qso-panel-' + (++panelIdCounter);

    const marker = new google.maps.Marker({
        position: position,
        map: map,
        icon: getMarkerIcon(isActive),
        zIndex: isActive ? 999 : 500,
    });

    if (isActive) {
        marker.setAnimation(google.maps.Animation.DROP);
    }

    const infoWindow = new google.maps.InfoWindow({
        content: createMiniPanelHtml(qso, isActive, panelId),
        disableAutoPan: true,
        pixelOffset: new google.maps.Size(0, -5),
    });

    const entry = {
        marker, infoWindow, qso,
        isDot: false,
        isActive: isActive,
        _infoOpen: showCard,
        _userOpened: false,
        _panelId: panelId,
        _iwL6: null,
        _guardedZ: null,
        _zObserver: null,
    };
    qsoEntries.push(entry);

    if (showCard) {
        infoWindow.open(map, marker);
    }

    google.maps.event.addListener(infoWindow, 'domready', () => {
        const panelEl = document.getElementById(entry._panelId);
        if (panelEl) {
            let el = panelEl;
            while (el && !el.classList.contains('gm-style-iw-a')) {
                el = el.parentElement;
            }
            if (el && el.parentElement) {
                entry._iwL6 = el.parentElement;
                // .gm-style-iw-a and .gm-style-iw-t are 9999px wide invisible wrappers.
                // Disable pointer events on them so clicks pass through to cards below,
                // then re-enable only on .gm-style-iw-c (the actual visible card).
                entry._iwL6.style.pointerEvents = 'none';
                el.style.pointerEvents = 'none';
                const iwT = el.querySelector('.gm-style-iw-t');
                if (iwT) iwT.style.pointerEvents = 'none';
                const iwC = el.querySelector('.gm-style-iw-c');
                if (iwC) iwC.style.pointerEvents = 'auto';
            }
            panelEl.style.cursor = 'pointer';
            panelEl.onclick = () => bringToFront(entry);
        }
        if (entry.isActive) {
            setZIndexGuard(entry, ACTIVE_ZINDEX);
        } else if (entry._guardedZ != null) {
            setZIndexGuard(entry, entry._guardedZ);
        } else {
            setZIndexGuard(entry, ++nextIwZIndex);
        }
    });

    marker.addListener('click', () => {
        if (entry._infoOpen) {
            clearZIndexGuard(entry);
            infoWindow.close();
            entry._infoOpen = false;
            entry._userOpened = false;
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
            entry._userOpened = true;
        }
    });
}

function createMiniPanelHtml(qso, isActive, panelId) {
    const cls = isActive ? 'active' : 'past';
    const dist = qso.distance_km.toLocaleString(undefined, { maximumFractionDigits: 0 });
    return `
        <div id="${panelId}" class="mini-panel ${cls}">
            <div class="mp-callsign">${escapeHtml(qso.callsign)}</div>
            <div class="mp-location">${escapeHtml(qso.city_name)}</div>
            <div class="mp-info">
                <span class="mp-distance">${dist} km</span>
                <span class="mp-band">${escapeHtml(qso.band)} ${escapeHtml(qso.mode)}</span>
            </div>
        </div>
    `;
}

function getMarkerIcon(isActive) {
    return isActive
        ? { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#00e676', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 2 }
        : { path: google.maps.SymbolPath.CIRCLE, scale: 6, fillColor: '#ffc107', fillOpacity: 0.9, strokeColor: '#ffffff', strokeWeight: 1 };
}

function getDotIcon() {
    return { path: google.maps.SymbolPath.CIRCLE, scale: 3, fillColor: '#888888', fillOpacity: 0.6, strokeColor: '#aaaaaa', strokeWeight: 1 };
}

function shrinkActivePanels() {
    qsoEntries.forEach(entry => {
        if (entry.isActive && !entry.isDot) {
            entry.isActive = false;
            clearZIndexGuard(entry);
            entry.marker.setIcon(getMarkerIcon(false));
            entry.marker.setZIndex(500);
            entry.infoWindow.setContent(createMiniPanelHtml(entry.qso, false, entry._panelId));
        }
    });
}

function enforceMaxPanels() {
    const autoOpen = qsoEntries.filter(e => e._infoOpen && !e._userOpened && !e.isActive);
    const excess = autoOpen.length - Math.max(0, MAX_OPEN_CARDS - 1);
    for (let i = 0; i < excess; i++) {
        const entry = autoOpen[i];
        clearZIndexGuard(entry);
        entry.isDot = true;
        entry.isActive = false;
        entry._infoOpen = false;
        entry.infoWindow.close();
        entry.marker.setIcon(getDotIcon());
        entry.marker.setZIndex(100);
    }
}

function clearAllMarkers() {
    qsoEntries.forEach(entry => {
        clearZIndexGuard(entry);
        entry.marker.setMap(null);
        entry.infoWindow.close();
    });
    qsoEntries.length = 0;
    farthestLines.forEach(line => line.setMap(null));
    farthestLines.length = 0;
}


/* ===== Zoom ===== */
function resetZoom() {
    if (!map) return;
    const bounds = new google.maps.LatLngBounds();
    bounds.extend({ lat: LOGMAP_CONFIG.stationLat, lng: LOGMAP_CONFIG.stationLon });
    qsoEntries.forEach(entry => bounds.extend(entry.marker.getPosition()));

    if (qsoEntries.length > 0) {
        map.fitBounds(bounds, { top: 60, bottom: 60, left: 40, right: 60 });
    } else {
        map.setCenter({ lat: LOGMAP_CONFIG.stationLat, lng: LOGMAP_CONFIG.stationLon });
        map.setZoom(6);
    }
}


/* ===== Statistics ===== */
function updateStats(stats) {
    document.getElementById('stats-total').textContent = stats.total_qsos || 0;
    document.getElementById('stats-farthest-call').textContent = stats.farthest_call || '-';
    document.getElementById('stats-farthest-location').textContent = stats.farthest_location || '-';
    const dist = stats.farthest_distance || 0;
    document.getElementById('stats-farthest-distance').textContent =
        dist > 0 ? `${dist.toLocaleString(undefined, { maximumFractionDigits: 0 })} km` : '- km';
}


/* ===== i18n ===== */
function setStatus(key) {
    document.getElementById('status-text').textContent = getTranslation(key);
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
        el.textContent = getTranslation(el.getAttribute('data-i18n'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        el.title = getTranslation(el.getAttribute('data-i18n-title'));
    });
    document.title = getTranslation('app_title');
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const lang = btn.getAttribute('data-lang');
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (socket && socket.connected) {
                socket.emit('change_language', { lang });
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
