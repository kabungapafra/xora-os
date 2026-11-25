// XORA: Firefox opens to its own home page, not Fedora's start page (loaded after Fedora's prefs)
pref("browser.startup.homepage", "about:home");
pref("startup.homepage_welcome_url", "");
pref("startup.homepage_override_url", "");

// XORA privacy defaults (users can still change them in Settings)
pref("datareporting.healthreport.uploadEnabled", false);
pref("datareporting.policy.dataSubmissionEnabled", false);
pref("toolkit.telemetry.enabled", false);
pref("toolkit.telemetry.unified", false);
pref("toolkit.telemetry.archive.enabled", false);
pref("app.shield.optoutstudies.enabled", false);
pref("app.normandy.enabled", false);
pref("browser.discovery.enabled", false);
pref("browser.newtabpage.activity-stream.feeds.telemetry", false);
pref("browser.newtabpage.activity-stream.telemetry", false);
pref("browser.newtabpage.activity-stream.showSponsored", false);
pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);
pref("extensions.pocket.enabled", false);
pref("browser.contentblocking.category", "strict");
pref("privacy.trackingprotection.enabled", true);
pref("privacy.trackingprotection.socialtracking.enabled", true);
pref("privacy.globalprivacycontrol.enabled", true);
pref("privacy.donottrackheader.enabled", true);
pref("dom.security.https_only_mode", true);
pref("network.dns.disablePrefetch", true);
pref("network.prefetch-next", false);
pref("browser.send_pings", false);
pref("geo.provider.use_geoclue", false);
