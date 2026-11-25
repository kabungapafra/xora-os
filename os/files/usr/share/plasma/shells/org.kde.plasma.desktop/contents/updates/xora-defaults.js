// XORA: default wallpaper on every desktop (runs once per user)
desktops().forEach(function (d) {
  d.wallpaperPlugin = "org.kde.image";
  d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
  d.writeConfig("Image", "file:///usr/share/wallpapers/XORA/");
  d.writeConfig("FillMode", "2");
});
