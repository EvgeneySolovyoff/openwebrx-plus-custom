(function () {
    'use strict';
    var started = false;

    function hidePluginUi() {
        var oldButton = document.getElementById('plugin-button-audio_filter');
        if (oldButton) oldButton.style.display = 'none';
        var oldWindow = document.getElementById('plugin-window-audio_filter');
        if (oldWindow) oldWindow.style.display = 'none';
        var oldToggle = document.getElementById('audio-filter-toggle-btn');
        if (oldToggle) oldToggle.style.display = 'none';
        var oldPanel = document.getElementById('audio-filter-floating-panel');
        if (oldPanel) oldPanel.style.display = 'none';
    }

    function syncControls() {
        hidePluginUi();
        var api = window.AudioFilterPlugin;
        var button = document.getElementById('openwebrx-nf-toggle');
        var slider = document.getElementById('openwebrx-panel-nf');
        if (!api || !button || !slider || typeof api.getNoiseReductionState !== 'function') return;
        var state = api.getNoiseReductionState();
        slider.disabled = !state.initialized || !state.enabled;
        if (document.activeElement !== slider) slider.value = state.strength;
        slider.title = 'NF noise reduction strength (' + state.strength + ' dB)';
        button.classList.toggle('highlighted', !!state.enabled);
        button.setAttribute('aria-pressed', state.enabled ? 'true' : 'false');
    }

    function init() {
        if (started) return true;
        started = true;
        syncControls();
        window.setInterval(syncControls, 500);
        return true;
    }

    if (typeof Plugins !== 'undefined') {
        Plugins.nf_bridge = Plugins.nf_bridge || {};
        Plugins.nf_bridge.no_css = true;
        Plugins.nf_bridge.init = init;
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
