/**
 * Signatur-Canvas: Unterschrift mit Finger, Stift oder Maus.
 * Unterstützt beliebig viele Felder gleichzeitig; gespeicherte Felder
 * werden ohne Seiten-Reload als "gespeichert" markiert, damit die
 * übrigen, noch nicht unterschriebenen Felder erhalten bleiben.
 */
(function () {
    'use strict';

    function initWidget(widget) {
        if (widget.getAttribute('data-sig-init') === '1') return;
        widget.setAttribute('data-sig-init', '1');

        var canvas = widget.querySelector('canvas.signature-pad');
        if (!canvas) return;
        var ctx = canvas.getContext('2d');
        var drawing = false;
        var hasInk = false;
        var last = null;

        function resize() {
            var ratio = window.devicePixelRatio || 1;
            var rect = canvas.getBoundingClientRect();
            if (rect.width === 0) return; // noch nicht sichtbar
            var image = hasInk ? canvas.toDataURL() : null;
            canvas.width = rect.width * ratio;
            canvas.height = rect.height * ratio;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.scale(ratio, ratio);
            ctx.lineWidth = 2.2;
            ctx.lineCap = 'round';
            ctx.strokeStyle = '#1A1A1A';
            if (image) {
                var img = new Image();
                img.onload = function () { ctx.drawImage(img, 0, 0, rect.width, rect.height); };
                img.src = image;
            }
        }
        resize();
        window.addEventListener('resize', resize);

        function pos(ev) {
            var rect = canvas.getBoundingClientRect();
            return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
        }
        canvas.addEventListener('pointerdown', function (ev) {
            ev.preventDefault();
            canvas.setPointerCapture(ev.pointerId);
            drawing = true;
            last = pos(ev);
        });
        canvas.addEventListener('pointermove', function (ev) {
            if (!drawing) return;
            ev.preventDefault();
            var p = pos(ev);
            ctx.beginPath();
            ctx.moveTo(last.x, last.y);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
            last = p;
            hasInk = true;
        });
        ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (t) {
            canvas.addEventListener(t, function () { drawing = false; });
        });

        widget.querySelector('[data-sig-clear]').addEventListener('click', function () {
            ctx.save();
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.restore();
            hasInk = false;
        });

        // Überschrift des Feldes folgt der gewählten Rolle
        var roleSelect = widget.querySelector('[name=signer_role]');
        var roleTitle = widget.querySelector('.sig-role-title');
        if (roleSelect && roleTitle) {
            roleSelect.addEventListener('change', function () {
                roleTitle.textContent = roleSelect.options[roleSelect.selectedIndex].text;
            });
        }

        widget.querySelector('[data-sig-save]').addEventListener('click', function () {
            var msg = widget.querySelector('.sig-message');
            if (!hasInk) {
                msg.textContent = 'Bitte zuerst unterschreiben.';
                return;
            }
            var payload = {
                image: canvas.toDataURL('image/png'),
                signer_name: (widget.querySelector('[name=signer_name]') || {}).value || '',
                signer_role: (widget.querySelector('[name=signer_role]') || {}).value || '',
                signed_location: (widget.querySelector('[name=signed_location]') || {}).value || '',
                comment: (widget.querySelector('[name=sig_comment]') || {}).value || '',
                participant_id: (widget.querySelector('[name=participant_id]') || {}).value || ''
            };
            msg.textContent = 'Unterschrift wird gespeichert …';
            window.upApi(widget.getAttribute('data-signature-widget'), payload).then(function (res) {
                if (res.ok) {
                    // Feld als gespeichert markieren, andere Felder bleiben erhalten
                    widget.classList.add('saved');
                    msg.innerHTML = '<span class="sig-saved-mark">✓ Unterschrift gespeichert</span>';
                    canvas.style.pointerEvents = 'none';
                    widget.querySelectorAll('input, select, [data-sig-save], [data-sig-clear]').forEach(function (el) {
                        el.disabled = true;
                    });
                    // Löschen-Button für die soeben gespeicherte Unterschrift anbieten
                    if (res.signature_id) {
                        var saveBase = widget.getAttribute('data-signature-widget').replace(/\/save$/, '');
                        var del = document.createElement('button');
                        del.type = 'button';
                        del.className = 'btn btn-sm btn-danger';
                        del.textContent = 'Unterschrift löschen';
                        del.setAttribute('data-sig-delete', saveBase + '/' + res.signature_id + '/delete');
                        msg.appendChild(document.createTextNode(' '));
                        msg.appendChild(del);
                    }
                    // Zähler der bereits erfassten Unterschriften mitführen
                    var count = document.getElementById('sig-count');
                    if (count) count.textContent = String(parseInt(count.textContent, 10) + 1);
                } else {
                    msg.textContent = res.error || 'Speichern fehlgeschlagen.';
                }
            }).catch(function () {
                msg.textContent = 'Speichern derzeit nicht möglich – bitte Verbindung prüfen.';
            });
        });
    }

    document.querySelectorAll('[data-signature-widget]').forEach(initWidget);

    // Weiteres Unterschriftsfeld hinzufügen
    var addBtn = document.getElementById('add-signature-pad');
    if (addBtn) {
        addBtn.addEventListener('click', function () {
            var tpl = document.getElementById('tpl-signature-pad');
            var grid = document.getElementById('signature-grid');
            var node = tpl.content.firstElementChild.cloneNode(true);
            grid.appendChild(node);
            initWidget(node);
            node.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
    }

    // Gespeicherte Signatur löschen
    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-sig-delete]');
        if (!btn) return;
        if (!window.confirm('Unterschrift wirklich löschen?')) return;
        window.upApi(btn.getAttribute('data-sig-delete'), {}).then(function (res) {
            if (res.ok) window.location.reload();
        });
    });
})();
