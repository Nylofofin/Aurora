import QtQuick 2.15
import QtQuick.Shapes 1.15

Item {
    id: root
    width: 136
    height: 136
    transformOrigin: Item.Center

    property string mode: "idle"
    property bool motionEnabled: false
    property real revealScale: 1.0
    property real inputLevel: 0.0
    property real speechPulse: 0.0
    property real completionPulse: 0.0
    property real pressX: 0
    property real pressY: 0
    property real windowStartX: 0
    property real windowStartY: 0
    property int windowX: 0
    property int windowY: 0
    property bool dragging: false

    readonly property color stateColor: ({
        listening: "#8DDBF4", thinking: "#AF9BE8", searching: "#82C6EE",
        weather: "#91CDE7", preparing: "#BAA5ED", speaking: "#D6C4F5",
        approval: "#E8C889", controlling: "#B2A0E2", error: "#E7A2B2", idle: "#A99AD8"
    })[mode] || "#A99AD8"
    property color animatedStateColor: stateColor
    property real tintStrength: mode === "listening" ? 0.34
        : mode === "speaking" ? 0.34
        : mode === "searching" ? 0.37
        : mode === "thinking" || mode === "preparing" || mode === "weather" ? 0.29 : 0.18
    readonly property real voiceEnergy: mode === "listening" ? inputLevel : 0.0
    readonly property real outputEnergy: mode === "speaking" ? Math.max(speechPulse, 0.10) : 0.0
    readonly property real activeEnergy: Math.max(voiceEnergy, outputEnergy, completionPulse)

    signal startVoice()
    signal hideRequested()
    signal quitRequested()
    signal positionChanged(int x, int y)
    signal dragMoved(int x, int y)

    scale: revealScale

    Behavior on tintStrength { NumberAnimation { duration: 320; easing.type: Easing.InOutCubic } }
    Behavior on animatedStateColor { ColorAnimation { duration: 360; easing.type: Easing.InOutCubic } }
    Behavior on inputLevel { SmoothedAnimation { velocity: 3.2; duration: 90; maximumEasingTime: 90 } }
    Behavior on speechPulse { NumberAnimation { duration: 82; easing.type: Easing.OutCubic } }
    Behavior on completionPulse { NumberAnimation { duration: 105; easing.type: Easing.OutCubic } }

    // Motion stays on the glass surface: a slow breath plus a moving internal
    // light field. No detached rings, particles or changing silhouette.
    Item {
        id: sphere
        x: 10; y: 10; width: 116; height: 116
        transformOrigin: Item.Center
        property real breathing: 0.0
        property real sheenTravel: 0.0
        scale: 0.99 + breathing * 0.012 + root.activeEnergy * 0.026
        Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

        SequentialAnimation on breathing {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation {
                from: 0; to: 1
                duration: root.mode === "searching" ? 1550
                    : root.mode === "thinking" || root.mode === "preparing" ? 2300 : 3500
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                from: 1; to: 0
                duration: root.mode === "searching" ? 1850
                    : root.mode === "thinking" || root.mode === "preparing" ? 2700 : 4100
                easing.type: Easing.InOutSine
            }
        }
        SequentialAnimation on sheenTravel {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation {
                from: -1; to: 1
                duration: root.mode === "searching" ? 2100
                    : root.mode === "thinking" || root.mode === "preparing" ? 3300 : 5100
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                from: 1; to: -1
                duration: root.mode === "searching" ? 2400
                    : root.mode === "thinking" || root.mode === "preparing" ? 3600 : 5600
                easing.type: Easing.InOutSine
            }
        }

        // Pearlescent shell with one quiet blue-to-violet tonal gradient.
        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: "#70FFFFFF"; strokeWidth: 1.0
                fillGradient: LinearGradient {
                    x1: 22; y1: 4; x2: 95; y2: 112
                    GradientStop { position: 0.00; color: "#FFFDFC" }
                    GradientStop { position: 0.19; color: "#EDF8FC" }
                    GradientStop { position: 0.42; color: "#BFEAF5" }
                    GradientStop { position: 0.66; color: "#91B9EF" }
                    GradientStop { position: 0.84; color: "#8C8CDE" }
                    GradientStop { position: 1.00; color: "#675BAF" }
                }
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56; startAngle: 0; sweepAngle: 360 }
            }
        }

        // State tint and internal color drift share one surface pass.
        Shape {
            anchors.fill: parent
            opacity: Math.min(0.72, root.tintStrength + root.activeEnergy * 0.13)
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 54 + sphere.sheenTravel * 13 + root.voiceEnergy * 6
                    centerY: 58 + sphere.breathing * 5
                    centerRadius: 66
                    focalX: 30 + sphere.sheenTravel * 10 - root.outputEnergy * 5
                    focalY: 24 + root.voiceEnergy * 3
                    focalRadius: 0
                    GradientStop { position: 0.00; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.60) }
                    GradientStop { position: 0.50; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.24) }
                    GradientStop { position: 1.00; color: "#00000000" }
                }
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56; startAngle: 0; sweepAngle: 360 }
            }
        }

        // A soft pearl highlight moves slowly; voice energy gently lifts it.
        Shape {
            x: 13 + sphere.sheenTravel * 4 + root.voiceEnergy * 3
            y: 5 + sphere.breathing * 2 - root.completionPulse * 2
            width: 88; height: 70
            opacity: Math.min(0.94, 0.68 + root.activeEnergy * 0.22)
            scale: 1.0 + root.activeEnergy * 0.035
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 44; centerY: 33; centerRadius: 44
                    focalX: 33 + sphere.sheenTravel * 3; focalY: 21; focalRadius: 0
                    GradientStop { position: 0.00; color: "#EFFFFFFF" }
                    GradientStop { position: 0.34; color: "#AFFFFFFF" }
                    GradientStop { position: 0.73; color: "#36FFFFFF" }
                    GradientStop { position: 1.00; color: "#00FFFFFF" }
                }
                PathAngleArc { centerX: 44; centerY: 34; radiusX: 43; radiusY: 33; startAngle: 0; sweepAngle: 360 }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: true
        onPressed: function(mouse) {
            if (mouse.button === Qt.RightButton) {
                if (mouse.modifiers & Qt.ShiftModifier) root.quitRequested()
                else root.hideRequested()
                mouse.accepted = true
                return
            }
            root.dragging = false
            root.pressX = mouse.x; root.pressY = mouse.y
            root.windowStartX = root.windowX; root.windowStartY = root.windowY
        }
        onPositionChanged: function(mouse) {
            if (!(mouse.buttons & Qt.LeftButton)) return
            const dx = mouse.x - root.pressX
            const dy = mouse.y - root.pressY
            if (!root.dragging && Math.abs(dx) + Math.abs(dy) > 7) {
                root.dragging = true
                root.dragMoved(root.windowStartX + dx, root.windowStartY + dy)
            } else if (root.dragging) {
                root.dragMoved(root.windowStartX + dx, root.windowStartY + dy)
            }
        }
        onReleased: function(mouse) {
            if (mouse.button !== Qt.LeftButton) return
            if (root.dragging) root.positionChanged(root.windowX, root.windowY)
            else root.startVoice()
            root.dragging = false
        }
    }
}
