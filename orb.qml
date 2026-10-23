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
    property real speechPulse: 0.18
    property real pressX: 0
    property real pressY: 0
    property real windowStartX: 0
    property real windowStartY: 0
    property int windowX: 0
    property int windowY: 0
    property bool dragging: false

    readonly property color stateColor: ({
        listening: "#8deaff", thinking: "#b89aff", searching: "#77d9ff",
        weather: "#8bdcff", preparing: "#c2a5ff", speaking: "#e2c5ff",
        approval: "#ffe0a1", controlling: "#b9a1ff", error: "#ff9dbb", idle: "#bba7ff"
    })[mode] || "#bba7ff"
    property color animatedStateColor: stateColor
    property real tintStrength: mode === "listening" ? 0.29
        : mode === "speaking" ? 0.34
        : mode === "searching" ? 0.32
        : mode === "thinking" || mode === "preparing" || mode === "weather" ? 0.25 : 0.14
    readonly property real voiceEnergy: mode === "listening" ? inputLevel : 0.0
    readonly property real outputEnergy: mode === "speaking" ? speechPulse : 0.0

    signal startVoice()
    signal hideRequested()
    signal quitRequested()
    signal positionChanged(int x, int y)
    signal dragMoved(int x, int y)

    scale: revealScale

    Behavior on tintStrength { NumberAnimation { duration: 420; easing.type: Easing.InOutCubic } }
    Behavior on animatedStateColor { ColorAnimation { duration: 460; easing.type: Easing.InOutCubic } }
    Behavior on inputLevel { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }

    // A single glass sphere. All motion and state cues stay on its surface.
    Item {
        id: sphere
        x: 11; y: 11; width: 114; height: 114
        transformOrigin: Item.Center
        property real breathing: 0.0
        property real sheenTravel: 0.0

        SequentialAnimation on breathing {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 1; duration: root.mode === "searching" ? 1900 : 3900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0; duration: root.mode === "searching" ? 2100 : 4500; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on scale {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation {
                from: root.mode === "speaking" ? 0.99 : 0.982
                to: root.mode === "speaking" ? 1.045 : 1.018
                duration: root.mode === "speaking" ? 360 : root.mode === "searching" ? 1250 : 3900
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                from: root.mode === "speaking" ? 1.045 : 1.018
                to: root.mode === "speaking" ? 0.99 : 0.982
                duration: root.mode === "speaking" ? 440 : root.mode === "searching" ? 1450 : 4500
                easing.type: Easing.InOutSine
            }
        }
        SequentialAnimation on sheenTravel {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: -1; to: 1; duration: root.mode === "searching" ? 1500 : root.mode === "thinking" ? 2800 : 6200; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: -1; duration: root.mode === "searching" ? 1800 : root.mode === "thinking" ? 3200 : 6900; easing.type: Easing.InOutSine }
        }

        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: "#baffffff"; strokeWidth: 1.0
                fillGradient: LinearGradient {
                    x1: 16; y1: 5; x2: 101; y2: 108
                    GradientStop { position: 0.00; color: "#fffefe" }
                    GradientStop { position: 0.16; color: "#ecfaff" }
                    GradientStop { position: 0.33; color: "#c9efff" }
                    GradientStop { position: 0.51; color: "#87d5ff" }
                    GradientStop { position: 0.69; color: "#587ffa" }
                    GradientStop { position: 0.85; color: "#725fe9" }
                    GradientStop { position: 1.00; color: "#5138b5" }
                }
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56; startAngle: 0; sweepAngle: 360 }
            }
        }

        // Soft state color and depth are blended into the sphere itself.
        Shape {
            anchors.fill: parent
            opacity: root.tintStrength
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 57 + sphere.sheenTravel * 11; centerY: 60; centerRadius: 64
                    focalX: 35 + sphere.sheenTravel * 9; focalY: 24; focalRadius: 0
                    GradientStop { position: 0.0; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.68) }
                    GradientStop { position: 0.56; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.32) }
                    GradientStop { position: 1.0; color: "#00000000" }
                }
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56; startAngle: 0; sweepAngle: 360 }
            }
        }
        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 59; centerY: 76; centerRadius: 57; focalX: 57; focalY: 67; focalRadius: 1
                    GradientStop { position: 0.0; color: "#586ac0ff" }
                    GradientStop { position: 0.48; color: "#3f657cff" }
                    GradientStop { position: 0.84; color: "#176454ff" }
                    GradientStop { position: 1.0; color: "#006454ff" }
                }
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 56; radiusY: 56; startAngle: 0; sweepAngle: 360 }
            }
        }

        // Pearl reflection sweeps over the orb; its response tracks voice
        // input/output without adding glyphs, dots, or detached indicators.
        Shape {
            x: 12 + sphere.sheenTravel * 3 + root.voiceEnergy * 2
            y: 4 + sphere.breathing * 2
            width: 88; height: 69
            opacity: 0.72 + root.voiceEnergy * 0.24 + root.outputEnergy * 0.18
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 43; centerY: 28; centerRadius: 43
                    focalX: 34 + sphere.sheenTravel * 2; focalY: 19; focalRadius: 0
                    GradientStop { position: 0.00; color: "#f0ffffff" }
                    GradientStop { position: 0.34; color: "#b5ffffff" }
                    GradientStop { position: 0.72; color: "#45ffffff" }
                    GradientStop { position: 1.00; color: "#00ffffff" }
                }
                PathAngleArc { centerX: 44; centerY: 34; radiusX: 43; radiusY: 33; startAngle: 0; sweepAngle: 360 }
            }
        }
        Rectangle {
            x: 19 + (sphere.sheenTravel + 1) * 14
            y: 17 + sphere.breathing * 1.5
            width: 58; height: 13; radius: 7; rotation: -20
            opacity: 0.45 + root.voiceEnergy * 0.28 + root.outputEnergy * 0.22
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.00; color: "#00ffffff" }
                GradientStop { position: 0.30; color: "#afffffff" }
                GradientStop { position: 0.62; color: "#76ffffff" }
                GradientStop { position: 1.00; color: "#00ffffff" }
            }
        }
        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: "#75ffffff"; strokeWidth: 1.1; fillColor: "transparent"
                PathAngleArc { centerX: 57; centerY: 57; radiusX: 54.5; radiusY: 54.5; startAngle: 205; sweepAngle: 128 }
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
