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
        listening: "#E8D9FF", thinking: "#C7AFE9", searching: "#9B7FC1",
        weather: "#DCCBFA", preparing: "#B49AD9", speaking: "#F5EDFF",
        approval: "#F4D888", controlling: "#735A8F", error: "#E59B9E", idle: "#674D87"
    }) : bubbleStyle === "io" ? ({
        listening: "#FFF0A6", thinking: "#FFC35E", searching: "#F47A50",
        weather: "#FFE18A", preparing: "#F39343", speaking: "#FFF4C7",
        approval: "#FFF0A6", controlling: "#BD5039", error: "#E76558", idle: "#A9423D"
    }) : bubbleStyle === "triton" ? ({
        listening: "#D6E3FF", thinking: "#9DB6F2", searching: "#5E80D8",
        weather: "#C3D6FF", preparing: "#86A1E5", speaking: "#EDF3FF",
        approval: "#F4D888", controlling: "#3157A2", error: "#ED9EA8", idle: "#203C7B"
    }) : ({
        listening: "#91E4F8", thinking: "#B7A4F2", searching: "#7ECDF5",
        weather: "#9DDCF0", preparing: "#C8B5F7", speaking: "#E2D2FF",
        approval: "#EBCB8B", controlling: "#A99AE8", error: "#EAA7BB", idle: "#A493D8"
    })
    // Keep one stable, circular silhouette for every finish. Style identity
    // comes from color, refraction and small surface details inside the glass.
    readonly property string orbPath: "M 57 1 A 56 56 0 1 1 57 113 A 56 56 0 1 1 57 1 Z"
    readonly property color stateColor: statePalette[mode] || statePalette.idle
    readonly property color styleBase: bubbleStyle === "emerald" ? "#EDFFF7" : bubbleStyle === "crimson" ? "#FFF4DF" : bubbleStyle === "amethyst" ? "#F4F2FF" : bubbleStyle === "solaris" ? "#FFF0F0" : bubbleStyle === "ocean" ? "#EAFFFF" : bubbleStyle === "titan" ? "#F4EFFF" : bubbleStyle === "io" ? "#FFE8A1" : bubbleStyle === "triton" ? "#EAF0FF" : "#EFFAFF"
    readonly property color styleMid: bubbleStyle === "emerald" ? "#B7EBDD" : bubbleStyle === "crimson" ? "#F2D398" : bubbleStyle === "amethyst" ? "#D0D5F4" : bubbleStyle === "solaris" ? "#EDB0BD" : bubbleStyle === "ocean" ? "#B3F0E4" : bubbleStyle === "titan" ? "#C7B9E4" : bubbleStyle === "io" ? "#F8C04E" : bubbleStyle === "triton" ? "#A6B9EE" : "#BFEAF5"
    readonly property color styleLow: bubbleStyle === "emerald" ? "#70D2AE" : bubbleStyle === "crimson" ? "#D78F57" : bubbleStyle === "amethyst" ? "#9CAEE7" : bubbleStyle === "solaris" ? "#D77F98" : bubbleStyle === "ocean" ? "#58CFC6" : bubbleStyle === "titan" ? "#76658F" : bubbleStyle === "io" ? "#EC633C" : bubbleStyle === "triton" ? "#3C65B0" : "#6CA9EC"
    readonly property color styleDeep: bubbleStyle === "emerald" ? "#247D70" : bubbleStyle === "crimson" ? "#B9654B" : bubbleStyle === "amethyst" ? "#47598F" : bubbleStyle === "solaris" ? "#A94F72" : bubbleStyle === "ocean" ? "#1D678E" : bubbleStyle === "titan" ? "#504062" : bubbleStyle === "io" ? "#B43F3D" : bubbleStyle === "triton" ? "#243E82" : "#6961C7"
    readonly property color styleBottom: bubbleStyle === "emerald" ? "#165A56" : bubbleStyle === "crimson" ? "#92513F" : bubbleStyle === "amethyst" ? "#2D3F70" : bubbleStyle === "solaris" ? "#552F62" : bubbleStyle === "ocean" ? "#124567" : bubbleStyle === "titan" ? "#30233F" : bubbleStyle === "io" ? "#702D3C" : bubbleStyle === "triton" ? "#101D4B" : "#4B479E"
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

    // Motion stays on the glass surface: a slow breath, moving refraction and
    // style-specific details. The silhouette remains circular for every skin.
    Item {
        id: sphere
        x: 10; y: 10; width: 116; height: 116
        transformOrigin: Item.Center
        property real breathing: 0.0
        property real sheenTravel: 0.0
        property real sway: 0.0
        property real surfaceFlow: 0.0
        property real refraction: 0.0
        property real orbitPhase: 0.0
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
                    : root.mode === "thinking" || root.mode === "preparing" ? 2300 : 2500
                easing.type: Easing.InOutSine
            }
            NumberAnimation {
                from: 1; to: 0
                duration: root.mode === "searching" ? 1850
                    : root.mode === "thinking" || root.mode === "preparing" ? 2700 : 2500
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
            NumberAnimation { from: 0; to: 1; duration: root.mode === "searching" ? 1900 : 5200; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0; duration: root.mode === "searching" ? 2200 : 5200; easing.type: Easing.InOutSine }
        }
        SequentialAnimation on refraction {
            running: root.motionEnabled
            loops: Animation.Infinite
            NumberAnimation { from: -1; to: 1; duration: root.mode === "speaking" ? 1800 : 3900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: -1; duration: root.mode === "speaking" ? 2100 : 4300; easing.type: Easing.InOutSine }
        }
        NumberAnimation on orbitPhase {
            running: root.motionEnabled && root.bubbleStyle === "amethyst"
            from: 0; to: 360; duration: 11900
            loops: Animation.Infinite; easing.type: Easing.Linear
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

    // Each finish gets its own surface signature. Only the orbital finish
    // carries a satellite; other skins use their own material details.
    Shape {
        visible: root.bubbleStyle === "boreal"
        x: 20 + sphere.surfaceFlow * 3; y: 39; width: 96; height: 61
        ShapePath {
            strokeColor: "#B0A5FFF0"; strokeWidth: 3.0; fillColor: "transparent"
            PathMove { x: 2; y: 41 }
            PathCubic { control1X: 22; control1Y: 2; control2X: 47; control2Y: 58; x: 94; y: 15 }
        }
        ShapePath {
            strokeColor: "#8AD6C8FF"; strokeWidth: 1.8; fillColor: "transparent"
            PathMove { x: 3; y: 55 }
            PathCubic { control1X: 26; control1Y: 19; control2X: 61; control2Y: 60; x: 92; y: 31 }
        }
        ShapePath {
            strokeColor: "#C7B9FFB0"; strokeWidth: 1.0; fillColor: "transparent"
            PathMove { x: 9; y: 29 }
            PathCubic { control1X: 30; control1Y: 5; control2X: 57; control2Y: 38; x: 88; y: 20 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "emerald"
        x: 22 + sphere.surfaceFlow * 1.4; y: 31; width: 92; height: 76
        ShapePath {
            strokeColor: sphere.breathing > 0.5 ? "#C8E9FFF7" : "#A8E9FFF7"; strokeWidth: 1.15; fillColor: "transparent"
            PathMove { x: 16; y: 10 }
            PathCubic { control1X: 33; control1Y: 15; control2X: 38; control2Y: 24; x: 46; y: 38 }
            PathCubic { control1X: 55; control1Y: 45; control2X: 66; control2Y: 41; x: 80; y: 31 }
            PathMove { x: 46; y: 38 }
            PathCubic { control1X: 42; control1Y: 51; control2X: 29; control2Y: 58; x: 18; y: 68 }
            PathMove { x: 46; y: 38 }
            PathCubic { control1X: 54; control1Y: 51; control2X: 62; control2Y: 65; x: 79; y: 68 }
            PathMove { x: 18; y: 68 }
            PathCubic { control1X: 24; control1Y: 61; control2X: 28; control2Y: 54; x: 31; y: 47 }
            PathMove { x: 80; y: 31 }
            PathCubic { control1X: 74; control1Y: 38; control2X: 72; control2Y: 42; x: 69; y: 47 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "crimson"
        x: 19 + sphere.surfaceFlow * 1.6; y: 40; width: 98; height: 61
        ShapePath {
            strokeColor: "#74FFF0C7"; strokeWidth: 4.0; fillColor: "transparent"
            PathMove { x: 1; y: 12 }
            PathCubic { control1X: 26; control1Y: 1; control2X: 68; control2Y: 20; x: 97; y: 8 }
        }
        ShapePath {
            strokeColor: "#5E92513F"; strokeWidth: 5.0; fillColor: "transparent"
            PathMove { x: 0; y: 28 }
            PathCubic { control1X: 25; control1Y: 19; control2X: 65; control2Y: 39; x: 98; y: 25 }
        }
        ShapePath {
            strokeColor: "#82FFE5B0"; strokeWidth: 3.0; fillColor: "transparent"
            PathMove { x: 1; y: 45 }
            PathCubic { control1X: 29; control1Y: 35; control2X: 68; control2Y: 55; x: 97; y: 42 }
        }
        ShapePath {
            strokeColor: "#5CFFF8E0"; strokeWidth: 0.8; fillColor: "transparent"
            PathMove { x: 6; y: 17 }
            PathCubic { control1X: 29; control1Y: 7; control2X: 62; control2Y: 24; x: 92; y: 11 }
            PathMove { x: 9; y: 52 }
            PathCubic { control1X: 31; control1Y: 42; control2X: 68; control2Y: 60; x: 90; y: 47 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "crimson"
        x: 68 + sphere.surfaceFlow * 5; y: 49 + sphere.breathing * 1.5; width: 24; height: 16
        ShapePath {
            strokeColor: "#C8FFDBB8"; strokeWidth: 1.0
            fillGradient: RadialGradient {
                centerX: 8; centerY: 6; centerRadius: 15
                GradientStop { position: 0; color: "#FFD39F" }
                GradientStop { position: 0.52; color: "#B94D41" }
                GradientStop { position: 1; color: "#007F3835" }
            }
            PathAngleArc { centerX: 12; centerY: 8; radiusX: 12; radiusY: 8; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {
            strokeColor: "#98FFE6B8"; strokeWidth: 0.75; fillColor: "transparent"
            PathMove { x: 2; y: 9 }
            PathCubic { control1X: 9; control1Y: 2; control2X: 18; control2Y: 2; x: 23; y: 8 }
            PathCubic { control1X: 17; control1Y: 14; control2X: 7; control2Y: 14; x: 2; y: 9 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "amethyst"
        x: 17; y: 39; width: 102; height: 58
        rotation: -24
        ShapePath {
            strokeColor: "#C6E5EAFF"; strokeWidth: 1.8; fillColor: "transparent"
            PathAngleArc { centerX: 51; centerY: 29; radiusX: 49; radiusY: 17; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {
            strokeColor: "#78B7CCFF"; strokeWidth: 0.9; fillColor: "transparent"
            PathAngleArc { centerX: 51; centerY: 29; radiusX: 44; radiusY: 13; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "amethyst"
        x: 68 + Math.cos(sphere.orbitPhase * Math.PI / 180) * 46 * Math.cos(-24 * Math.PI / 180) - Math.sin(sphere.orbitPhase * Math.PI / 180) * 16 * Math.sin(-24 * Math.PI / 180) - 4
        y: 68 + Math.cos(sphere.orbitPhase * Math.PI / 180) * 46 * Math.sin(-24 * Math.PI / 180) + Math.sin(sphere.orbitPhase * Math.PI / 180) * 16 * Math.cos(-24 * Math.PI / 180) - 4
        width: 8; height: 8
        ShapePath {
            strokeColor: "#E8FFFFFF"; strokeWidth: 0.8; fillColor: "#F8FBFF"
            PathAngleArc { centerX: 4; centerY: 4; radiusX: 3.5; radiusY: 3.5; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "solaris"
        x: 39 + sphere.surfaceFlow * 2.0; y: 38; width: 58; height: 58
        ShapePath {
            strokeColor: "#B0FFD0C9"; strokeWidth: 1.0
            fillGradient: RadialGradient {
                centerX: 22; centerY: 20; centerRadius: 34
                GradientStop { position: 0; color: "#DFFFF0DF" }
                GradientStop { position: 0.82; color: "#FFE8A4AF" }
                GradientStop { position: 1; color: "#00D77F98" }
            }
            PathAngleArc { centerX: 29; centerY: 29; radiusX: 28; radiusY: 28; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {
            strokeColor: "#70FFFFFF"; strokeWidth: 0.6; fillColor: "#F5532D5E"
            PathAngleArc { centerX: 39; centerY: 25; radiusX: 27; radiusY: 27; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "ocean"
        x: 24 + sphere.surfaceFlow * 2.5; y: 30; width: 88; height: 76
        ShapePath {
            strokeColor: "#DEE9FFFC"; strokeWidth: 2.1; fillColor: "transparent"
            PathMove { x: 5; y: 8 }
            PathLine { x: 30; y: 25 }
            PathLine { x: 24; y: 36 }
            PathLine { x: 48; y: 48 }
            PathLine { x: 43; y: 57 }
            PathLine { x: 78; y: 72 }
        }
        ShapePath {
            strokeColor: "#8274F4E6"; strokeWidth: 0.9; fillColor: "transparent"
            PathMove { x: 12; y: 6 }
            PathLine { x: 69; y: 69 }
        }
        ShapePath {
            strokeColor: "#BFFFFFFF"; strokeWidth: 1.1; fillColor: "transparent"
            PathMove { x: 30; y: 25 }
            PathLine { x: 17; y: 37 }
            PathLine { x: 11; y: 50 }
            PathMove { x: 48; y: 48 }
            PathLine { x: 61; y: 37 }
            PathLine { x: 74; y: 35 }
            PathMove { x: 43; y: 57 }
            PathLine { x: 58; y: 63 }
            PathLine { x: 72; y: 62 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "titan"
        x: 18 + sphere.surfaceFlow * 2.2; y: 27; width: 102; height: 77
        ShapePath {
            strokeColor: "#B8FFE4B5"; strokeWidth: 3.2; fillColor: "transparent"
            PathMove { x: 1; y: 24 }
            PathCubic { control1X: 27; control1Y: 6; control2X: 69; control2Y: 33; x: 101; y: 17 }
        }
        ShapePath {
            strokeColor: "#84FFF0C7"; strokeWidth: 2.0; fillColor: "transparent"
            PathMove { x: 0; y: 39 }
            PathCubic { control1X: 23; control1Y: 25; control2X: 66; control2Y: 52; x: 100; y: 33 }
        }
        ShapePath {
            strokeColor: "#55FFEABF"; strokeWidth: 1.1; fillColor: "transparent"
            PathMove { x: 6; y: 55 }
            PathCubic { control1X: 32; control1Y: 42; control2X: 75; control2Y: 69; x: 96; y: 51 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "io"
        x: 64 + sphere.surfaceFlow * 2; y: 30; width: 34; height: 76
        ShapePath {
            strokeColor: "#C25F252D"; strokeWidth: 4.0; fillColor: "transparent"
            PathMove { x: 23; y: 2 }
            PathCubic { control1X: 4; control1Y: 19; control2X: 28; control2Y: 29; x: 13; y: 44 }
            PathCubic { control1X: 3; control1Y: 55; control2X: 24; control2Y: 62; x: 8; y: 74 }
        }
        ShapePath {
            strokeColor: sphere.breathing > 0.5 ? "#8AFFE28A" : "#CCFFE28A"; strokeWidth: 1.4; fillColor: "transparent"
            PathMove { x: 23; y: 2 }
            PathCubic { control1X: 4; control1Y: 19; control2X: 28; control2Y: 29; x: 13; y: 44 }
            PathCubic { control1X: 3; control1Y: 55; control2X: 24; control2Y: 62; x: 8; y: 74 }
            PathMove { x: 14; y: 44 }
            PathCubic { control1X: 25; control1Y: 45; control2X: 27; control2Y: 52; x: 32; y: 57 }
            PathMove { x: 19; y: 34 }
            PathCubic { control1X: 10; control1Y: 30; control2X: 7; control2Y: 25; x: 2; y: 22 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "triton"
        x: 24; y: 24; width: 88; height: 40
        ShapePath {
            strokeColor: "#C6E9FAFF"; strokeWidth: 1.0; fillColor: "#5CC6E9FF"
            PathMove { x: 2; y: 30 }
            PathCubic { control1X: 8; control1Y: 5; control2X: 29; control2Y: 1; x: 43; y: 9 }
            PathCubic { control1X: 57; control1Y: 1; control2X: 77; control2Y: 9; x: 86; y: 30 }
            PathCubic { control1X: 68; control1Y: 20; control2X: 55; control2Y: 35; x: 43; y: 26 }
            PathCubic { control1X: 28; control1Y: 19; control2X: 14; control2Y: 35; x: 2; y: 30 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "triton"
        x: 31 + sphere.surfaceFlow * 2; y: 44; width: 73; height: 48
        ShapePath {
            strokeColor: "#D9F5FFFF"; strokeWidth: 1.7; fillColor: "transparent"
            PathMove { x: 2; y: 24 }
            PathCubic { control1X: 22; control1Y: 41; control2X: 51; control2Y: 3; x: 72; y: 20 }
        }
        ShapePath {
            strokeColor: "#738FE3FF"; strokeWidth: 0.9; fillColor: "transparent"
            PathMove { x: 9; y: 37 }
            PathCubic { control1X: 25; control1Y: 44; control2X: 47; control2Y: 12; x: 67; y: 30 }
        }
    }
    Shape {
        visible: root.bubbleStyle === "triton"
        x: 72 + Math.sin(sphere.surfaceFlow * Math.PI * 2) * 2; y: 38 - sphere.breathing * 4; width: 22; height: 34
        ShapePath {
            strokeColor: "#D9F6FFFF"; strokeWidth: 1.2; fillColor: "transparent"
            PathMove { x: 11; y: 34 }
            PathCubic { control1X: 5; control1Y: 21; control2X: 16; control2Y: 12; x: 11; y: 1 }
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
