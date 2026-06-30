/**
 * RFIDScanner — keyboard-wedge driver for Chainway C72 Bluetooth scanner.
 *
 * The C72 sends each scanned tag as a string followed by a Return keystroke,
 * exactly like a keyboard. This class buffers keystrokes, fires on Enter,
 * validates the tag format, and exposes a clean callback API.
 *
 * Usage:
 *   const scanner = new RFIDScanner({ onScan: (tag) => console.log(tag) });
 *   scanner.start();
 *   // later…
 *   scanner.stop();
 *   const tags = scanner.getTags();
 */
class RFIDScanner {
    /**
     * @param {object}   opts
     * @param {function} opts.onScan       Called with (tagString) after each valid scan
     * @param {function} [opts.onDuplicate] Called with (tagString) when the same tag is scanned again
     * @param {function} [opts.onInvalid]   Called with (rawString) when a scan fails validation
     * @param {RegExp}   [opts.tagPattern]  Override the default tag validation pattern
     * @param {number}   [opts.bufferTimeout] ms — reset the buffer if no keystroke arrives (default 500)
     */
    constructor(opts = {}) {
        this._onScan       = opts.onScan       || (() => {});
        this._onDuplicate  = opts.onDuplicate  || (() => {});
        this._onInvalid    = opts.onInvalid    || (() => {});
        this._tagPattern   = opts.tagPattern   || /^RR-\d{3,}$/;
        this._bufferTimeout = opts.bufferTimeout || 500;

        this._buffer  = '';
        this._timer   = null;
        this._tags    = [];
        this._tagSet  = new Set();
        this._active  = false;

        this._handleKey = this._handleKey.bind(this);
    }

    /** Attach the keyboard listener. */
    start() {
        if (this._active) return;
        this._active = true;
        document.addEventListener('keypress', this._handleKey);
    }

    /** Detach the keyboard listener. */
    stop() {
        if (!this._active) return;
        this._active = false;
        document.removeEventListener('keypress', this._handleKey);
        this._clearTimer();
        this._buffer = '';
    }

    /** Return a copy of all unique valid tags scanned so far. */
    getTags() {
        return [...this._tags];
    }

    /** Clear the accumulated tag list (does not stop the scanner). */
    clearTags() {
        this._tags   = [];
        this._tagSet = new Set();
    }

    // ── internals ────────────────────────────────────────────────

    _handleKey(e) {
        if (e.key === 'Enter') {
            this._flush();
            return;
        }
        // Ignore non-printable keys
        if (e.key.length !== 1) return;

        this._buffer += e.key;
        this._resetTimer();
    }

    _flush() {
        const raw = this._buffer.trim().toUpperCase();
        this._buffer = '';
        this._clearTimer();

        if (!raw) return;

        if (!this._tagPattern.test(raw)) {
            this._onInvalid(raw);
            return;
        }

        if (this._tagSet.has(raw)) {
            this._onDuplicate(raw);
            return;
        }

        this._tagSet.add(raw);
        this._tags.push(raw);
        this._onScan(raw);
    }

    _resetTimer() {
        this._clearTimer();
        this._timer = setTimeout(() => {
            // Stale partial buffer — discard silently
            this._buffer = '';
        }, this._bufferTimeout);
    }

    _clearTimer() {
        if (this._timer !== null) {
            clearTimeout(this._timer);
            this._timer = null;
        }
    }
}
