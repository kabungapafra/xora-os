/*
    XORA lock screen clock, laid out like GNOME/Ubuntu: the date above a large, light clock, and
    "Click or press a key to unlock" under it. It shows while the screen is idle and fades out when
    the password prompt appears (GNOME does the same).

    SPDX-License-Identifier: GPL-2.0-or-later
*/

import QtQuick
import QtQuick.Layouts

import org.kde.plasma.clock as PlasmaClock
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

Item {
    id: root

    // set by LockScreenUi: true while the password prompt is on screen
    property bool promptVisible: false
    // LockScreenUi expects these on its clock
    property Item shadow: null

    implicitWidth: column.implicitWidth
    implicitHeight: column.implicitHeight
    width: implicitWidth
    height: implicitHeight

    readonly property real base: Kirigami.Theme.defaultFont.pointSize

    ColumnLayout {
        id: column
        anchors.centerIn: parent
        spacing: 0
        opacity: root.promptVisible ? 0 : 1
        Behavior on opacity {
            NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.InOutQuad }
        }

        PlasmaComponents3.Label {           // Thursday 26 November
            text: Qt.formatDate(timeSource.dateTime, "dddd d MMMM")
            textFormat: Text.PlainText
            color: "white"
            font.pointSize: Math.round(root.base * 1.6)
            Layout.alignment: Qt.AlignHCenter
        }
        PlasmaComponents3.Label {           // 06:25
            text: Qt.formatTime(timeSource.dateTime, Qt.locale().timeFormat(Locale.ShortFormat).replace(/:ss/, ""))
            textFormat: Text.PlainText
            color: "white"
            font.pointSize: Math.round(root.base * 6.4)
            font.weight: Font.Light
            font.features: ({ "tnum": 1 })
            renderType: Text.NativeRendering
            Layout.alignment: Qt.AlignHCenter
        }
        PlasmaComponents3.Label {
            text: "Click or press a key to unlock"
            textFormat: Text.PlainText
            color: Qt.rgba(1, 1, 1, 0.85)
            font.pointSize: root.base
            Layout.topMargin: Kirigami.Units.gridUnit * 3
            Layout.alignment: Qt.AlignHCenter
        }
    }

    PlasmaClock.Clock {
        id: timeSource
        trackSeconds: false
    }
}
