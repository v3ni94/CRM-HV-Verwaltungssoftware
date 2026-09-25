/**
 * U-Protokoll – Client-Logik: Autosave, Teildatensätze, Uploads, Sortierung.
 * Bewusst ohne Framework; funktioniert in allen modernen Mobil-Browsern.
 */
(function () {
    'use strict';

    var csrf = document.querySelector('meta[name="csrf-token"]');
    var CSRF = csrf ? csrf.getAttribute('content') : '';
    var body = document.body;

    function api(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRF-Token': CSRF,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(data || {})
        }).then(function (r) { return r.json(); });
    }
    window.upApi = api;

    // ------------------------------------------------------------------
    // Autosave für Protokollfelder (data-autosave am Formular)
    // ------------------------------------------------------------------
    var autosaveForm = document.querySelector('form[data-autosave]');
    var statusEl = document.querySelectorAll('.autosave-status');
    var pending = {};
    var timer = null;
    var OFFLINE_KEY = null;

    function setStatus(text, isError) {
        statusEl.forEach(function (el) {
            el.textContent = text;
            el.classList.toggle('error', !!isError);
        });
    }

    function flushAutosave() {
        if (!autosaveForm) return;
        var fields = pending;
        if (Object.keys(fields).length === 0) return;
        pending = {};
        setStatus('Änderungen werden gespeichert …');
        api(autosaveForm.getAttribute('data-autosave'), { fields: fields })
            .then(function (res) {
                if (res.ok) {
                    setStatus('Gespeichert um ' + res.saved_at + ' Uhr');
                    if (OFFLINE_KEY) { try { localStorage.removeItem(OFFLINE_KEY); } catch (e) {} }
                } else {
                    setStatus(res.error || 'Speichern derzeit nicht möglich.', true);
                }
            })
            .catch(function () {
                // Verbindungsproblem: lokal zwischenspeichern, später erneut senden
                Object.assign(pending, fields);
                if (OFFLINE_KEY) {
                    try { localStorage.setItem(OFFLINE_KEY, JSON.stringify(pending)); } catch (e) {}
                }
                setStatus('Speichern derzeit nicht möglich – Daten bleiben lokal zwischengespeichert.', true);
            });
    }

    if (autosaveForm) {
        OFFLINE_KEY = 'uprotokoll_offline_' + autosaveForm.getAttribute('data-autosave');
        // Nach Wiederherstellung der Verbindung lokale Daten synchronisieren
        try {
            var saved = localStorage.getItem(OFFLINE_KEY);
            if (saved) { pending = JSON.parse(saved) || {}; flushAutosave(); }
        } catch (e) {}

        // Nur echte Protokollfelder erfassen; Teildatensätze (.record-card)
        // und Unterschriftsfelder haben eigene Speicherwege
        function isAutosaveField(el) {
            if (!el.name || el.name.charAt(0) === '_') return false;
            if (el.closest('.record-card') || el.closest('[data-signature-widget]')) return false;
            return true;
        }
        autosaveForm.addEventListener('change', function (ev) {
            var el = ev.target;
            if (!isAutosaveField(el)) return;
            pending[el.name] = (el.type === 'checkbox') ? (el.checked ? '1' : '0') : el.value;
            flushAutosave();
        });
        autosaveForm.addEventListener('input', function (ev) {
            var el = ev.target;
            if (!isAutosaveField(el)) return;
            pending[el.name] = el.value;
            clearTimeout(timer);
            timer = setTimeout(flushAutosave, 2500);
        });
        // Zusätzlich periodisch
        setInterval(flushAutosave, 20000);
        window.addEventListener('online', flushAutosave);
    }

    // ------------------------------------------------------------------
    // Teildatensätze: .record-card mit data-entity/data-record-id.
    // Felder werden bei Änderung sofort gespeichert (upsert).
    // ------------------------------------------------------------------
    function collectRecord(card) {
        var data = {};
        card.querySelectorAll('input, select, textarea').forEach(function (el) {
            if (!el.name) return;
            if (el.type === 'file') return;
            // Verschachtelte Datensätze (z. B. Mängel im Raum) nicht mit erfassen
            if (el.closest('.record-card') !== card) return;
            data[el.name] = (el.type === 'checkbox') ? (el.checked ? '1' : '0') : el.value;
        });
        return data;
    }

    function saveRecord(card) {
        var container = card.closest('[data-record-container]');
        if (!container) return Promise.resolve();
        var entity = container.getAttribute('data-entity');
        var base = container.getAttribute('data-base');
        var data = collectRecord(card);
        data.record_id = card.getAttribute('data-record-id') || '';
        setStatus('Änderungen werden gespeichert …');
        return api(base + '/record/' + entity + '/save', data).then(function (res) {
            if (res.ok) {
                card.setAttribute('data-record-id', res.record_id);
                // Upload-Zonen im Datensatz mit der neuen ID versorgen
                card.querySelectorAll('[data-needs-record]').forEach(function (zone) {
                    zone.setAttribute('data-ref-value', res.record_id);
                });
                setStatus('Gespeichert um ' + res.saved_at + ' Uhr');
                if (res.warning) { setStatus(res.warning, true); }
            } else {
                setStatus(res.error || 'Speichern fehlgeschlagen.', true);
            }
            return res;
        }).catch(function () {
            setStatus('Speichern derzeit nicht möglich – bitte Verbindung prüfen.', true);
        });
    }
    window.upSaveRecord = saveRecord;

    body.addEventListener('change', function (ev) {
        var card = ev.target.closest('.record-card');
        if (card && card.closest('[data-record-container]') && !ev.target.closest('[data-no-recordsave]')) {
            saveRecord(card);
        }
    });

    // Datensatz hinzufügen: Vorlage aus <template> klonen und sofort anlegen
    body.addEventListener('click', function (ev) {
        var addBtn = ev.target.closest('[data-add-record]');
        if (addBtn) {
            ev.preventDefault();
            var container = document.querySelector(addBtn.getAttribute('data-add-record'));
            var tpl = document.getElementById(container.getAttribute('data-template'));
            var node = tpl.content.firstElementChild.cloneNode(true);
            container.appendChild(node);
            var preset = addBtn.getAttribute('data-preset');
            if (preset) {
                var presetData = JSON.parse(preset);
                Object.keys(presetData).forEach(function (name) {
                    var el = node.querySelector('[name="' + name + '"]');
                    if (el) el.value = presetData[name];
                });
            }
            if (window.upPrefillDateTime) window.upPrefillDateTime(node);
            if (window.upInjectMoveButtons) window.upInjectMoveButtons(node);
            saveRecord(node);
            node.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        var delBtn = ev.target.closest('[data-delete-record]');
        if (delBtn) {
            ev.preventDefault();
            if (!window.confirm('Diesen Eintrag wirklich löschen?')) return;
            var card = delBtn.closest('.record-card');
            var container = card.closest('[data-record-container]');
            var id = card.getAttribute('data-record-id');
            if (!id) { card.remove(); return; }
            api(container.getAttribute('data-base') + '/record/' + container.getAttribute('data-entity') + '/delete', { record_id: id })
                .then(function (res) { if (res.ok) card.remove(); else alert(res.error || 'Löschen fehlgeschlagen.'); });
        }

        var dupBtn = ev.target.closest('[data-duplicate-room]');
        if (dupBtn) {
            ev.preventDefault();
            var roomCard = dupBtn.closest('.record-card');
            var roomId = roomCard.getAttribute('data-record-id');
            if (!roomId) return;
            api(dupBtn.getAttribute('data-duplicate-room') + '/rooms/' + roomId + '/duplicate', {})
                .then(function (res) { if (res.ok) window.location.reload(); });
        }
    });

    // Raumzustand: Mängelbereich nur bei "Mängel vorhanden" anzeigen
    body.addEventListener('change', function (ev) {
        if (ev.target.matches('select[name="condition_status"]')) {
            var card = ev.target.closest('.record-card');
            var defectsArea = card && card.querySelector('.defects-area');
            if (defectsArea) defectsArea.hidden = ev.target.value !== 'defective';
        }
    });

    // ------------------------------------------------------------------
    // Datei-Upload (Mehrfach, Kamera, Drag & Drop) je .upload-zone
    // ------------------------------------------------------------------
    function uploadFiles(zone, files) {
        var base = zone.getAttribute('data-upload-url');
        var statusBox = zone.querySelector('.upload-status');
        var list = zone.parentElement.querySelector('.thumb-list');
        // Neuer Datensatz noch nicht gespeichert: erst auf die Datensatz-ID warten
        if (zone.getAttribute('data-needs-record') === '1' && !zone.getAttribute('data-ref-value')) {
            statusBox.textContent = 'Der Eintrag wird gerade angelegt. Bitte einen Moment warten und erneut versuchen.';
            statusBox.className = 'upload-status failed';
            return;
        }
        Array.prototype.forEach.call(files, function (file) {
            var fd = new FormData();
            fd.append('files[]', file);
            fd.append('category', zone.getAttribute('data-category') || 'photo');
            fd.append('_token', CSRF);
            var refField = zone.getAttribute('data-ref-field');
            var refValue = zone.getAttribute('data-ref-value');
            if (refField && refValue) fd.append(refField, refValue);
            if (zone.getAttribute('data-internal') === '1') fd.append('is_internal', '1');
            var attachmentType = zone.getAttribute('data-attachment-type');
            var typeSelect = zone.parentElement.querySelector('select[data-attachment-type-select]');
            if (typeSelect) attachmentType = typeSelect.value;
            if (attachmentType) fd.append('attachment_type', attachmentType);
            var descInput = zone.parentElement.querySelector('input[data-file-description]');
            if (descInput && descInput.value) fd.append('description', descInput.value);

            statusBox.textContent = file.name + ' wird hochgeladen …';
            statusBox.className = 'upload-status';
            fetch(base, { method: 'POST', body: fd, headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    if (res.ok && res.files.length) {
                        statusBox.textContent = 'Erfolgreich hochgeladen.';
                        res.files.forEach(function (f) { addThumb(list, f); });
                    } else {
                        var msg = res.error || ((res.errors && res.errors[0]) ? res.errors[0].error : 'Upload fehlgeschlagen.');
                        statusBox.textContent = file.name + ': ' + msg + ' Bitte erneut versuchen.';
                        statusBox.className = 'upload-status failed';
                    }
                })
                .catch(function () {
                    statusBox.textContent = file.name + ': Upload fehlgeschlagen – erneut versuchen.';
                    statusBox.className = 'upload-status failed';
                });
        });
    }

    function addThumb(list, f) {
        if (!list) return;
        var item = document.createElement('div');
        item.className = 'thumb-item';
        item.setAttribute('data-file-id', f.id);
        var isImage = f.mime && f.mime.indexOf('image/') === 0;
        item.innerHTML = (isImage
            ? '<a href="' + f.url + '" target="_blank" rel="noopener"><img src="' + f.thumbUrl + '" alt=""></a>'
            : '<a class="thumb-doc" href="' + f.url + '" target="_blank" rel="noopener"></a>')
            + '<button type="button" class="thumb-del" title="Löschen">×</button>';
        if (!isImage) item.querySelector('.thumb-doc').textContent = f.name || 'Dokument';
        list.appendChild(item);
    }

    body.addEventListener('change', function (ev) {
        if (ev.target.matches('.upload-zone input[type=file]')) {
            var zone = ev.target.closest('.upload-zone');
            uploadFiles(zone, ev.target.files);
            ev.target.value = '';
        }
    });
    body.addEventListener('dragover', function (ev) {
        var zone = ev.target.closest('.upload-zone');
        if (zone) { ev.preventDefault(); zone.classList.add('dragover'); }
    });
    body.addEventListener('dragleave', function (ev) {
        var zone = ev.target.closest('.upload-zone');
        if (zone) zone.classList.remove('dragover');
    });
    body.addEventListener('drop', function (ev) {
        var zone = ev.target.closest('.upload-zone');
        if (zone) {
            ev.preventDefault();
            zone.classList.remove('dragover');
            if (ev.dataTransfer.files.length) uploadFiles(zone, ev.dataTransfer.files);
        }
    });

    // Datei löschen
    body.addEventListener('click', function (ev) {
        var del = ev.target.closest('.thumb-del');
        if (!del) return;
        if (!window.confirm('Datei wirklich löschen?')) return;
        var item = del.closest('.thumb-item');
        var base = document.querySelector('[data-protocol-base]');
        if (!base) return;
        api(base.getAttribute('data-protocol-base') + '/files/' + item.getAttribute('data-file-id') + '/delete', {})
            .then(function (res) { if (res.ok) item.remove(); else alert(res.error || 'Löschen nicht möglich.'); });
    });

    // ------------------------------------------------------------------
    // Sortierung: Drag & Drop am Desktop, Auf/Ab-Buttons für Touch-Geräte
    // ------------------------------------------------------------------
    function saveOrder(container) {
        var order = Array.prototype.map.call(container.querySelectorAll(':scope > .record-card'), function (c) {
            return c.getAttribute('data-record-id');
        }).filter(Boolean);
        api(container.getAttribute('data-base') + '/record/' + container.getAttribute('data-entity') + '/sort', { order: order })
            .then(function (res) {
                if (!res.ok) setStatus(res.error || 'Sortierung konnte nicht gespeichert werden.', true);
            })
            .catch(function () {
                setStatus('Sortierung konnte nicht gespeichert werden. Bitte Verbindung prüfen.', true);
            });
    }

    // Auf/Ab-Buttons in sortierbaren Karten ergänzen (funktioniert auch per Touch,
    // da natives HTML5-Drag auf Mobilgeräten nicht verfügbar ist)
    function injectMoveButtons(card) {
        var container = card.closest('[data-record-container][data-sortable]');
        if (!container || card.parentElement !== container) return;
        var handle = card.querySelector('.drag-handle');
        if (!handle || card.querySelector('[data-move-up]')) return;
        var up = document.createElement('button');
        up.type = 'button';
        up.className = 'btn btn-sm btn-secondary';
        up.setAttribute('data-move-up', '1');
        up.title = 'Nach oben';
        up.textContent = '▲';
        var down = document.createElement('button');
        down.type = 'button';
        down.className = 'btn btn-sm btn-secondary';
        down.setAttribute('data-move-down', '1');
        down.title = 'Nach unten';
        down.textContent = '▼';
        handle.after(up, down);
    }
    window.upInjectMoveButtons = injectMoveButtons;
    document.querySelectorAll('[data-record-container][data-sortable] > .record-card').forEach(injectMoveButtons);

    body.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-move-up], [data-move-down]');
        if (!btn) return;
        ev.preventDefault();
        var card = btn.closest('.record-card');
        var container = card.closest('[data-record-container][data-sortable]');
        if (!container) return;
        if (btn.hasAttribute('data-move-up') && card.previousElementSibling) {
            container.insertBefore(card, card.previousElementSibling);
        } else if (btn.hasAttribute('data-move-down') && card.nextElementSibling) {
            container.insertBefore(card.nextElementSibling, card);
        } else {
            return;
        }
        saveOrder(container);
    });

    document.querySelectorAll('[data-record-container][data-sortable]').forEach(function (container) {
        var dragged = null;
        container.addEventListener('dragstart', function (ev) {
            var card = ev.target.closest('.record-card');
            if (!card) return;
            dragged = card;
            card.classList.add('dragging');
        });
        container.addEventListener('dragend', function () {
            if (!dragged) return;
            dragged.classList.remove('dragging');
            dragged = null;
            saveOrder(container);
        });
        container.addEventListener('dragover', function (ev) {
            ev.preventDefault();
            if (!dragged) return;
            var after = null;
            container.querySelectorAll('.record-card:not(.dragging)').forEach(function (c) {
                var rect = c.getBoundingClientRect();
                if (ev.clientY < rect.top + rect.height / 2 && after === null) after = c;
            });
            if (after) container.insertBefore(dragged, after); else container.appendChild(dragged);
        });
    });

    // Alle-auswählen-Checkbox (Sammel-Archivierung in der Übersicht)
    body.addEventListener('change', function (ev) {
        if (!ev.target.matches('[data-check-all]')) return;
        var form = ev.target.closest('form');
        if (!form) return;
        form.querySelectorAll('input[name="ids[]"]').forEach(function (cb) {
            cb.checked = ev.target.checked;
        });
    });

    // ------------------------------------------------------------------
    // Datums-/Zeitfelder mit aktuellem Zeitpunkt vorbelegen
    // ------------------------------------------------------------------
    function pad2(n) { return (n < 10 ? '0' : '') + n; }
    function todayValue() {
        var d = new Date();
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
    }
    function nowTimeValue() {
        var d = new Date();
        return pad2(d.getHours()) + ':' + pad2(d.getMinutes());
    }
    function prefillDateTime(root) {
        root.querySelectorAll('input[type=date]').forEach(function (el) {
            if (!el.value) el.value = todayValue();
        });
        root.querySelectorAll('input[type=time]').forEach(function (el) {
            if (!el.value) el.value = nowTimeValue();
        });
    }
    window.upPrefillDateTime = prefillDateTime;
    // Nur Protokollfelder (z. B. Übergabedatum) beim Laden vorbelegen und speichern.
    // Bestehende Teildatensätze aus der Datenbank bleiben unangetastet, damit
    // bewusst leer gelassene Werte nicht stillschweigend befüllt werden;
    // neue Datensätze werden beim Hinzufügen vorbelegt (siehe data-add-record).
    if (autosaveForm) {
        var changedPrefill = false;
        autosaveForm.querySelectorAll('input[type=date], input[type=time]').forEach(function (el) {
            if (el.value || !el.name || el.name.charAt(0) === '_') return;
            if (el.closest('.record-card') || el.closest('[data-signature-widget]')) return;
            el.value = el.type === 'date' ? todayValue() : nowTimeValue();
            pending[el.name] = el.value;
            changedPrefill = true;
        });
        if (changedPrefill) flushAutosave();
    }

    // ------------------------------------------------------------------
    // Ort per GPS vorbelegen (nur mit Zustimmung; sonst bleibt das Feld leer)
    // ------------------------------------------------------------------
    (function () {
        var targets = Array.prototype.filter.call(
            document.querySelectorAll('input[name="signed_location"], input[name="handover_location"]'),
            function (el) { return !el.value; }
        );
        if (!targets.length || !navigator.geolocation) return;
        navigator.geolocation.getCurrentPosition(function (pos) {
            fetch('https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=16&lat='
                    + pos.coords.latitude + '&lon=' + pos.coords.longitude, { headers: { 'Accept': 'application/json' } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var a = data.address || {};
                    var city = a.city || a.town || a.village || a.municipality || '';
                    var street = a.road ? a.road + (a.house_number ? ' ' + a.house_number : '') : '';
                    var text = city ? (street ? street + ', ' + city : city) : (data.display_name || '');
                    if (!text) return;
                    targets.forEach(function (el) {
                        if (!el.value) {
                            el.value = text;
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                })
                .catch(function () { /* Ort bleibt zur manuellen Eingabe leer */ });
        }, function () { /* abgelehnt oder nicht verfügbar: Feld bleibt leer */ }, { timeout: 8000, maximumAge: 300000 });
    })();

    // Klickbare Zeilen/Karten der Protokollliste
    body.addEventListener('click', function (ev) {
        var row = ev.target.closest('.row-click');
        if (!row) return;
        // Klicks auf Checkboxen, Links und Buttons nicht abfangen
        if (ev.target.closest('a, button, input, label, select')) return;
        var href = row.getAttribute('data-href');
        if (href) window.location.href = href;
    });

    // Abschluss-Bestätigungsdialog
    var completeForm = document.querySelector('form[data-confirm-complete]');
    if (completeForm) {
        completeForm.addEventListener('submit', function (ev) {
            if (!window.confirm('Das Protokoll wird abgeschlossen und als PDF erzeugt. Möchten Sie fortfahren?')) {
                ev.preventDefault();
            }
        });
    }
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (ev) {
            if (!window.confirm(form.getAttribute('data-confirm'))) ev.preventDefault();
        });
    });
})();
