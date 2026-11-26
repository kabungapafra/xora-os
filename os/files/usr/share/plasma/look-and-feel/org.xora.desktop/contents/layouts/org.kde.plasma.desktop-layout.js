// XORA desktop layout (applied on a user's first login), from the XORA design:
//   top bar:  [XORA logo · Space: name ▾]      [Wed 25 Nov · 11:58]      [Fabric · 3 devices] [Data] [tray: wifi, sound, battery]
//   dock:     centred, floating: [launcher X] | Files · Browser · Terminal · Spaces · Settings

// ---- wallpaper on every desktop
var desktopsArray = desktopsForActivity(currentActivity());
for (var j = 0; j < desktopsArray.length; j++) {
    var d = desktopsArray[j];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file:///usr/share/wallpapers/XORA/");
    d.writeConfig("FillMode", "2");
}

// ---- top bar
var top = new Panel;
top.location = "top";
top.height = 2 * Math.ceil(gridUnit * 1.8 / 2);
top.floating = false;

top.addWidget("org.xora.spaces");
top.addWidget("org.kde.plasma.panelspacer");

var clock = top.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateFormat", "custom");
clock.writeConfig("customDateFormat", "ddd d MMM ·");
clock.writeConfig("dateDisplayFormat", "BesideTime");

top.addWidget("org.kde.plasma.panelspacer");
top.addWidget("org.xora.fabric");
top.addWidget("org.xora.anon");
top.addWidget("org.xora.datasaver");
top.addWidget("org.kde.plasma.systemtray");

// ---- dock
var dock = new Panel;
dock.location = "bottom";
dock.height = 2 * Math.ceil(gridUnit * 3.2 / 2);
dock.alignment = "center";
dock.lengthMode = "fit";
dock.floating = true;
dock.hiding = "dodgewindows";

var tasks = dock.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:org.xora.Center.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:org.mozilla.firefox.desktop",
    "applications:org.gnome.Ptyxis.desktop",
    "applications:systemsettings.desktop"
].join(","));
tasks.writeConfig("showOnlyCurrentDesktop", false);

dock.addWidget("org.kde.plasma.marginsseparator");

// "Show Applications" (like Ubuntu's grid button): every app and tool full-screen, with search and categories.
// Super+A opens it too (like Ubuntu); Super alone opens the Overview of windows (kwinrc).
var grid = dock.addWidget("org.kde.plasma.kickerdash");
grid.currentConfigGroup = ["General"];
grid.writeConfig("useCustomButtonImage", true);
grid.writeConfig("customButtonImage", "view-app-grid-symbolic");
grid.writeConfig("showRecentApps", false);
grid.writeConfig("showRecentDocs", false);
// favourites at the top of the grid: XORA's own apps, not KDE's defaults (Konsole is replaced by Ptyxis)
grid.writeConfig("favoritesPortedToKAstats", false);
grid.writeConfig("favorites", ["org.xora.Center.desktop", "org.gnome.Ptyxis.desktop", "org.kde.dolphin.desktop",
                               "org.mozilla.firefox.desktop", "org.kde.discover.desktop", "systemsettings.desktop"].join(","));
grid.globalShortcut = "Meta+A";
