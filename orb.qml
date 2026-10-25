// SPDX-License-Identifier: GPL-3.0-only
import QtQuick 2.15
import QtQuick.Shapes 1.15

Item {
    id: root
    width: 136
    height: 136
    transformOrigin: Item.Center

    property string mode: "idle"
    property string bubbleStyle: "boreal"
    property bool motionEnabled: false
    property real revealScale: 1.0
    property real inputLevel: 0.0
    property real speechPulse: 0.0
    property real completionPulse: 0.0
    property real hoverEnergy: 0.0
    property real pressX: 0
    property real pressY: 0
    property real windowStartX: 0
    property real windowStartY: 0
    property int windowX: 0
    property int windowY: 0
    property bool dragging: false

    readonly property var statePalette: bubbleStyle === "emerald" ? ({
        listening: "#8AF5C2", thinking: "#45E0A4", searching: "#22C997",
        weather: "#75E7B1", preparing: "#38D58A", speaking: "#B0F8D2",
        approval: "#F3D77C", controlling: "#14B87A", error: "#F29B80", idle: "#31C98D"
    }) : bubbleStyle === "crimson" ? ({
        listening: "#FFE49A", thinking: "#FFC85C", searching: "#F2A83D",
        weather: "#FFD37A", preparing: "#F4B24B", speaking: "#FFF0BB",
        approval: "#FFF0A6", controlling: "#DC8C2C", error: "#F28B75", idle: "#D8822D"
    }) : bubbleStyle === "amethyst" ? ({
        listening: "#D6DEFF", thinking: "#AEBDF4", searching: "#869DE2",
        weather: "#C8D5FF", preparing: "#A7B8EE", speaking: "#EFF0FF",
        approval: "#F4D38A", controlling: "#6878BE", error: "#F39BCA", idle: "#626BB2"
    }) : bubbleStyle === "solaris" ? ({
        listening: "#F5C5D2", thinking: "#DFA2B4", searching: "#B97D9B",
        weather: "#F1B9CC", preparing: "#D38CA8", speaking: "#FFE6EA",
        approval: "#F4D38A", controlling: "#9A6488", error: "#F39BCA", idle: "#6D4A80"
    }) : bubbleStyle === "ocean" ? ({
        listening: "#9DF4F5", thinking: "#50D8E7", searching: "#2AB9D4",
        weather: "#8DE7F0", preparing: "#49C9DD", speaking: "#C9FAFF",
        approval: "#F4D888", controlling: "#218EBD", error: "#F18E9C", idle: "#258FC2"
    }) : ({
        listening: "#91E4F8", thinking: "#B7A4F2", searching: "#7ECDF5",
        weather: "#9DDCF0", preparing: "#C8B5F7", speaking: "#E2D2FF",
        approval: "#EBCB8B", controlling: "#A99AE8", error: "#EAA7BB", idle: "#A493D8"
    })
    readonly property string orbPath: bubbleStyle === "emerald"
        ? "M 57 1 C 79 1 93 7 105 20 C 116 32 115 46 115 57 C 115 79 109 94 96 105 C 84 116 69 115 57 115 C 35 115 21 109 9 96 C -2 84 -1 69 -1 57 C -1 35 5 21 18 9 C 30 -2 45 1 57 1 Z"
        : bubbleStyle === "ocean"
        ? "M 57 1 C 84 12 111 31 108 59 C 106 82 77 108 62 114 C 54 117 45 112 37 105 C 15 86 4 67 7 48 C 10 27 35 9 57 1 Z"
        : "M 57 1 A 56 56 0 1 1 57 113 A 56 56 0 1 1 57 1 Z"
    readonly property color stateColor: statePalette[mode] || statePalette.idle
    readonly property color styleBase: bubbleStyle === "emerald" ? "#E9FFF7" : bubbleStyle === "crimson" ? "#FFF8E8" : bubbleStyle === "amethyst" ? "#F6F5FF" : bubbleStyle === "solaris" ? "#FFF4F6" : bubbleStyle === "ocean" ? "#EDFFFF" : "#EDF8FC"
    readonly property color styleMid: bubbleStyle === "emerald" ? "#BCEBDD" : bubbleStyle === "crimson" ? "#F2D49B" : bubbleStyle === "amethyst" ? "#D2D8F8" : bubbleStyle === "solaris" ? "#E7B8C6" : bubbleStyle === "ocean" ? "#A5E8E5" : "#BFEAF5"
    readonly property color styleLow: bubbleStyle === "emerald" ? "#70CBB0" : bubbleStyle === "crimson" ? "#E4AC68" : bubbleStyle === "amethyst" ? "#A6B4E5" : bubbleStyle === "solaris" ? "#BB88A6" : bubbleStyle === "ocean" ? "#61C6CE" : "#91B9EF"
    readonly property color styleDeep: bubbleStyle === "emerald" ? "#328F86" : bubbleStyle === "crimson" ? "#C77848" : bubbleStyle === "amethyst" ? "#737FBF" : bubbleStyle === "solaris" ? "#805477" : bubbleStyle === "ocean" ? "#397DA6" : "#8078DD"
    readonly property color styleBottom: bubbleStyle === "emerald" ? "#206A68" : bubbleStyle === "crimson" ? "#985244" : bubbleStyle === "amethyst" ? "#4D568D" : bubbleStyle === "solaris" ? "#583D68" : bubbleStyle === "ocean" ? "#245B83" : "#4C46A8"
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
    Behavior on hoverEnergy { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    // Motion stays on the glass surface: a slow breath plus a moving internal
    // light field. No detached rings, particles or changing silhouette.
    Item {
        id: sphere
        x: 10; y: 10; width: 116; height: 116
        transformOrigin: Item.Center
        property real breathing: 0.0
        property real sheenTravel: 0.0
        property real sway: 0.0
        property real surfaceFlow: 0.0
        property real refraction: 0.0
        scale: 0.99 + breathing * 0.012 + root.activeEnergy * 0.026 + root.hoverEnergy * 0.008
        // A restrained tilt and counter-tilt sell a living glass surface while
        // keeping the silhouette perfectly round to the eye.
        rotation: sway * 1.15 + root.activeEnergy * 1.4
        Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on rotation { NumberAnimation { duration: 260; easing.type: Easing.InOutSine } }

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
        SequentialAnimation on sway {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: -1; to: 1; duration: 3900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: -1; duration: 4300; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on surfaceFlow {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 1; duration: root.mode === "searching" ? 1900 : 3200; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0; duration: root.mode === "searching" ? 2200 : 3600; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on refraction {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: -1; to: 1; duration: root.mode === "speaking" ? 1800 : 3900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: -1; duration: root.mode === "speaking" ? 2100 : 4300; easing.type: Easing.InOutSine }
        }

        // Pearlescent shell with a style-specific tonal gradient.
        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: Qt.rgba(root.stateColor.r, root.stateColor.g, root.stateColor.b, 0.42); strokeWidth: 1.0
                fillGradient: LinearGradient {
                    x1: 22; y1: 4; x2: 95; y2: 112
                    GradientStop { position: 0.00; color: "#FFFDFC" }
                    GradientStop { position: 0.19; color: root.styleBase }
                    GradientStop { position: 0.42; color: root.styleMid }
                    GradientStop { position: 0.66; color: root.styleLow }
                    GradientStop { position: 0.84; color: root.styleDeep }
                    GradientStop { position: 1.00; color: root.styleBottom }
                }
                PathSvg { path: root.orbPath }
            }
        }

        // State tint and internal color drift share one surface pass.
        Shape {
            anchors.fill: parent
            opacity: Math.min(0.72, root.tintStrength + root.activeEnergy * 0.13)
            ShapePath {
                strokeColor: "transparent"; strokeWidth: 0
                fillGradient: RadialGradient {
                    centerX: 54 + sphere.sheenTravel * 13 + sphere.refraction * 8 + root.voiceEnergy * 6
                    centerY: 58 + sphere.breathing * 5 + sphere.surfaceFlow * 8
                    centerRadius: 66
                    focalX: 30 + sphere.sheenTravel * 10 - root.outputEnergy * 5
                    focalY: 24 + root.voiceEnergy * 3
                    focalRadius: 0
                    GradientStop { position: 0.00; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.60) }
                    GradientStop { position: 0.50; color: Qt.rgba(root.animatedStateColor.r, root.animatedStateColor.g, root.animatedStateColor.b, 0.24) }
                    GradientStop { position: 1.00; color: "#00000000" }
                }
                PathSvg { path: root.orbPath }
            }
        }

        // A soft pearl highlight moves slowly; voice energy gently lifts it.
        Shape {
            x: 13 + sphere.sheenTravel * 4 + sphere.surfaceFlow * 5 + sphere.refraction * 5 + root.voiceEnergy * 3
            y: 5 + sphere.breathing * 2 + sphere.surfaceFlow * 2 - root.completionPulse * 2
            rotation: sphere.refraction * 2.5
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

    // Planet-specific accents remain small and attached to the glass body.
    Rectangle {
        visible: root.bubbleStyle === "emerald"
        x: 27; y: 27; width: 82; height: 82
        rotation: -8 + sphere.sway * 0.8
        radius: 30
        color: "transparent"
        border.color: "#FFFFFF72"
        border.width: 1.2
    }
    Shape {
        visible: root.bubbleStyle === "amethyst" || root.bubbleStyle === "solaris"
        x: 3; y: 43 + sphere.sway; width: 130; height: 52
        rotation: (root.bubbleStyle === "amethyst" ? -19 : -31) + sphere.sway * 0.8
        ShapePath {
            strokeColor: root.bubbleStyle === "amethyst" ? "#DCD9FFB0" : "#F2D5E2B8"
            strokeWidth: 1.6; fillColor: "transparent"
            PathAngleArc { centerX: 65; centerY: 26; radiusX: 62; radiusY: 23; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "amethyst" || root.bubbleStyle === "solaris"
        x: 99 + sphere.sway * 0.5; y: 30 - sphere.sway * 0.35; width: 14; height: 14
        ShapePath {
            strokeColor: "#FFFFFF90"; strokeWidth: 0.6
            fillGradient: RadialGradient {
                centerX: 4; centerY: 3; centerRadius: 12
                GradientStop { position: 0; color: "#FFFFFF" }
                GradientStop { position: 1; color: root.bubbleStyle === "amethyst" ? "#A9B4E8" : "#C78DAD" }
            }
            PathAngleArc { centerX: 7; centerY: 7; radiusX: 6.5; radiusY: 6.5; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "crimson"
        x: 83 + sphere.surfaceFlow * 1.2; y: 76; width: 25; height: 16
        ShapePath {
            strokeColor: "#FFE4B099"; strokeWidth: 0.8
            fillGradient: RadialGradient {
                centerX: 7; centerY: 5; centerRadius: 20
                GradientStop { position: 0; color: "#E79572" }
                GradientStop { position: 1; color: "#A94E48" }
            }
            PathAngleArc { centerX: 12; centerY: 8; radiusX: 11; radiusY: 6; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "ocean"
        x: 19; y: 37; width: 97; height: 69
        rotation: -27 + sphere.sway * 0.7
        ShapePath {
            strokeColor: "#EDFFFFA8"; strokeWidth: 1.7; fillColor: "transparent"
            PathAngleArc { centerX: 48; centerY: 34; radiusX: 39; radiusY: 28; startAngle: 24; sweepAngle: 72 }
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
        onEntered: root.hoverEnergy = 1.0
        onExited: root.hoverEnergy = 0.0
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
