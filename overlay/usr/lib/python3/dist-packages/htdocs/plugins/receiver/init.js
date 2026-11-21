var rigHadSavedTheme = (typeof LS !== "undefined" && LS.has("ui_theme"));
var rigHadSavedWidth = (typeof LS !== "undefined" && LS.has("rig_wide_user"));

if (typeof LS !== "undefined") {
    if (rigHadSavedWidth === false) LS.save("rig_wide_user", false);
    if (LS.has("ui_frame") === false) LS.save("ui_frame", false);
    if (LS.has("ui_wheel") === false) LS.save("ui_wheel", false);
    if (LS.has("ui_crossfreq") === false) LS.save("ui_crossfreq", true);
    if (LS.has("ui_bandplan") === false) LS.save("ui_bandplan", true);
    if (LS.has("ui_spectrum") === false) LS.save("ui_spectrum", true);
}

Plugins.load(window.location.origin + "/static/plugins/receiver/rig_skin_v88/rig_skin.js?v=drms-sat-20261025g-stereo3").then(function () {
    if (rigHadSavedTheme === false && typeof UI !== "undefined" && typeof UI.setTheme === "function") {
        UI.setTheme("rig");
    }
    if (typeof LS !== "undefined" && LS.has("wf_theme") === false && typeof UI !== "undefined" && typeof UI.setWfTheme === "function") {
        UI.setWfTheme("rig");
    }
});

Plugins.load(window.location.origin + "/static/plugins/receiver/audio_filter/audio_filter.js").then(function () {
    return Plugins.load(window.location.origin + "/static/plugins/receiver/audio_filter/nf_bridge.js");
});
