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
    }) : bubbleStyle === "titan" ? ({
        listening: "#E7E4FF", thinking: "#B6B9E8", searching: "#9298D4",
        weather: "#D7D9F6", preparing: "#AEB3DF", speaking: "#F3F0FF",
        approval: "#F4D888", controlling: "#68709F", error: "#E59B9E", idle: "#626B9B"
    }) : bubbleStyle === "io" ? ({
        listening: "#FFF0A6", thinking: "#FFC35E", searching: "#FF8750",
        weather: "#FFE18A", preparing: "#F6A84E", speaking: "#FFF4C7",
        approval: "#FFF0A6", controlling: "#D96939", error: "#E76558", idle: "#C75A3C"
    }) : bubbleStyle === "triton" ? ({
        listening: "#C7F8FF", thinking: "#8CD9F1", searching: "#4DB9E0",
        weather: "#B6F0FA", preparing: "#72CDE9", speaking: "#E4FCFF",
        approval: "#F4D888", controlling: "#397EBC", error: "#ED9EA8", idle: "#376FA9"
    }) : ({
        listening: "#91E4F8", thinking: "#B7A4F2", searching: "#7ECDF5",
        weather: "#9DDCF0", preparing: "#C8B5F7", speaking: "#E2D2FF",
        approval: "#EBCB8B", controlling: "#A99AE8", error: "#EAA7BB", idle: "#A493D8"
    })
    // Keep one stable, circular silhouette for every finish. Style identity
    // comes from color, refraction and small surface details inside the glass.
    readonly property string orbPath: "M 57 1 A 56 56 0 1 1 57 113 A 56 56 0 1 1 57 1 Z"
    readonly property color stateColor: statePalette[mode] || statePalette.idle
    readonly property color styleBase: bubbleStyle === "emerald" ? "#E9FFF7" : bubbleStyle === "crimson" ? "#FFF8E8" : bubbleStyle === "amethyst" ? "#F6F5FF" : bubbleStyle === "solaris" ? "#FFF4F6" : bubbleStyle === "ocean" ? "#EDFFFF" : bubbleStyle === "titan" ? "#F4F3FF" : bubbleStyle === "io" ? "#FFF9E3" : bubbleStyle === "triton" ? "#F0FDFF" : "#EDF8FC"
    readonly property color styleMid: bubbleStyle === "emerald" ? "#BCEBDD" : bubbleStyle === "crimson" ? "#F2D49B" : bubbleStyle === "amethyst" ? "#D2D8F8" : bubbleStyle === "solaris" ? "#E7B8C6" : bubbleStyle === "ocean" ? "#A5E8E5" : bubbleStyle === "titan" ? "#C3C6E2" : bubbleStyle === "io" ? "#FFE69B" : bubbleStyle === "triton" ? "#B8EDF0" : "#BFEAF5"
    readonly property color styleLow: bubbleStyle === "emerald" ? "#70CBB0" : bubbleStyle === "crimson" ? "#E4AC68" : bubbleStyle === "amethyst" ? "#A6B4E5" : bubbleStyle === "solaris" ? "#BB88A6" : bubbleStyle === "ocean" ? "#61C6CE" : bubbleStyle === "titan" ? "#7E86B7" : bubbleStyle === "io" ? "#F1A34A" : bubbleStyle === "triton" ? "#64C4DF" : "#91B9EF"
    readonly property color styleDeep: bubbleStyle === "emerald" ? "#328F86" : bubbleStyle === "crimson" ? "#C77848" : bubbleStyle === "amethyst" ? "#737FBF" : bubbleStyle === "solaris" ? "#805477" : bubbleStyle === "ocean" ? "#397DA6" : bubbleStyle === "titan" ? "#4B527E" : bubbleStyle === "io" ? "#ED7041" : bubbleStyle === "triton" ? "#397DB7" : "#8078DD"
    readonly property color styleBottom: bubbleStyle === "emerald" ? "#206A68" : bubbleStyle === "crimson" ? "#985244" : bubbleStyle === "amethyst" ? "#4D568D" : bubbleStyle === "solaris" ? "#583D68" : bubbleStyle === "ocean" ? "#245B83" : bubbleStyle === "titan" ? "#292D49" : bubbleStyle === "io" ? "#8D3540" : bubbleStyle === "triton" ? "#243A73" : "#4C46A8"
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
        x: 34; y: 34; width: 68; height: 68
        rotation: -8 + sphere.sway * 0.8
        radius: 24
        color: "transparent"
        border.color: "#FFFFFF72"
        border.width: 1.2
    }
    Shape {
        visible: root.bubbleStyle === "amethyst" || root.bubbleStyle === "solaris"
        x: 23; y: 50 + sphere.sway; width: 90; height: 36
        rotation: (root.bubbleStyle === "amethyst" ? -19 : -31) + sphere.sway * 0.8
        ShapePath {
            strokeColor: root.bubbleStyle === "amethyst" ? "#DCD9FFB0" : "#F2D5E2B8"
            strokeWidth: 1.6; fillColor: "transparent"
            PathAngleArc { centerX: 45; centerY: 18; radiusX: 42; radiusY: 15; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "amethyst" || root.bubbleStyle === "solaris"
        x: 93 + sphere.sway * 0.5; y: 35 - sphere.sway * 0.35; width: 12; height: 12
        ShapePath {
            strokeColor: "#FFFFFF90"; strokeWidth: 0.6
            fillGradient: RadialGradient {
                centerX: 4; centerY: 3; centerRadius: 12
                GradientStop { position: 0; color: "#FFFFFF" }
                GradientStop { position: 1; color: root.bubbleStyle === "amethyst" ? "#A9B4E8" : "#C78DAD" }
            }
            PathAngleArc { centerX: 6; centerY: 6; radiusX: 5.5; radiusY: 5.5; startAngle: 0; sweepAngle: 360 }
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
    Shape {
        visible: root.bubbleStyle === "titan"
        x: 19; y: 31; width: 98; height: 75
        rotation: -18 + sphere.sway * 0.45
        ShapePath {
            strokeColor: "#F6D79D90"; strokeWidth: 2.2; fillColor: "transparent"
            PathAngleArc { centerX: 49; centerY: 37; radiusX: 46; radiusY: 29; startAngle: 205; sweepAngle: 136 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "titan"
        x: 78 + sphere.sway * 0.25; y: 82; width: 11; height: 11
        ShapePath {
            strokeColor: "#FFFFFFAA"; strokeWidth: 0.7; fillColor: "#F5DCA8"
            PathAngleArc { centerX: 5.5; centerY: 5.5; radiusX: 5; radiusY: 5; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "io"
        x: 64 + sphere.surfaceFlow * 1.3; y: 32; width: 30; height: 69
        ShapePath {
            strokeColor: "#8D3540C8"; strokeWidth: 3.0; fillColor: "transparent"
            PathMove { x: 19; y: 2 }
            PathCubic { control1X: 4; control1Y: 19; control2X: 27; control2Y: 28; x: 13; y: 42 }
            PathCubic { control1X: 3; control1Y: 52; control2X: 21; control2Y: 57; x: 8; y: 68 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "io"
        x: 82; y: 31; width: 10; height: 10
        ShapePath {
            strokeColor: "#FFFFFFB0"; strokeWidth: 0.6; fillColor: "#FFF1B2"
            PathAngleArc { centerX: 5; centerY: 5; radiusX: 4.5; radiusY: 4.5; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "triton"
        x: 20; y: 39; width: 96; height: 63
        rotation: -12 + sphere.sway * 0.45
        ShapePath {
            strokeColor: "#F1FFFFC8"; strokeWidth: 2.2; fillColor: "transparent"
            PathAngleArc { centerX: 48; centerY: 31; radiusX: 43; radiusY: 27; startAngle: 212; sweepAngle: 116 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "triton"
        x: 28; y: 45; width: 80; height: 51
        rotation: -12 + sphere.sway * 0.45
        ShapePath {
            strokeColor: "#BDEEF780"; strokeWidth: 1.1; fillColor: "transparent"
            PathAngleArc { centerX: 40; centerY: 25; radiusX: 35; radiusY: 22; startAngle: 212; sweepAngle: 116 }
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
