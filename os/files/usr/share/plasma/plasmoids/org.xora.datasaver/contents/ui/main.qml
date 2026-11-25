import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5S
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation
    toolTipMainText: root.st.metered ? "Data saver is on" : "Data saver is off"
    toolTipSubText: (root.st.data_today_h || "?") + " used " + (root.st.data_label || "") +
                    (root.st.metered ? ". Updates and big downloads wait until you're on a cheaper connection." : ". Click to save data.")
// runs `xora …` and other commands; JSON from `xora status --json` lands in root.st
    P5S.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            if (source === root.statusCmd) {
                try { root.st = JSON.parse(data["stdout"]) } catch (e) { }
            }
            disconnectSource(source)
        }
        function run(cmd) { connectSource(cmd) }
    }
    readonly property string statusCmd: "xora status --json"
    property var st: ({})
    function refresh() { exec.run(statusCmd) }
    function konsole(args) { exec.run("xora-term " + args) }
    Timer { interval: 8000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }

    // a popup is required: Plasma gives a panel widget without one no space
    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 16
        PC3.Label { text: root.st.metered ? "Data saver is on" : "Data saver is off"; font.bold: true }
        PC3.Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap
            text: (root.st.data_today_h || "?") + " used " + (root.st.data_label || "") + ". " +
                  (root.st.metered ? "Updates and big downloads wait until you're on a cheaper connection."
                                   : "Turn it on when you're on mobile data or an expensive connection.")
        }
        PC3.Button {
            text: root.st.metered ? "Turn Data saver off" : "Turn Data saver on"
            onClicked: { exec.run("xora data --metered " + (root.st.metered ? "off" : "on")); root.expanded = false }
        }
    }

    compactRepresentation: MouseArea {
        id: compact
        Layout.minimumWidth: r.implicitWidth + 8
        Layout.preferredWidth: Layout.minimumWidth
        hoverEnabled: true
        onClicked: {
            exec.run("xora data --metered " + (root.st.metered ? "off" : "on"))
            root.st = Object.assign({}, root.st, { metered: !root.st.metered })
            refreshSoon.restart()
        }
        Timer { id: refreshSoon; interval: 1500; onTriggered: root.refresh() }
        RowLayout {
            id: r
            anchors.centerIn: parent
            spacing: 6
            Kirigami.Icon { source: root.st.metered ? "smartphone" : "download"; implicitWidth: 14; implicitHeight: 14; color: root.st.metered ? "#FBBF24" : "#C3CAD6"; isMask: true }
            PC3.Label {
                text: root.st.metered ? "Data saver · " + (root.st.data_today_h || "") + " " + (root.st.data_label || "")
                                      : "Data · " + (root.st.data_today_h || "…")
                color: root.st.metered ? "#FDE68A" : "#C3CAD6"
                font.pixelSize: 12
            }
        }
    }
}
