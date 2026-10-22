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
    property bool dragging: false
    property real pressX: 0
    property real pressY: 0
    property real windowStartX: 0
    property real windowStartY: 0
    property int windowX: 0
    property int windowY: 0

    signal startVoice()
    signal hideRequested()
    signal quitRequested()
    signal positionChanged(int x, int y)
    signal dragMoved(int x, int y)

    scale: revealScale

    readonly property string statusText: ({
        listening: "OUVINDO", thinking: "PENSANDO", searching: "BUSCANDO",
        weather: "CLIMA", preparing: "PREPARANDO", speaking: "FALANDO",
        approval: "AUTORIZAR", controlling: "CONTROLANDO", error: "ERRO", idle: "PRONTA"
    })[mode] || "PRONTA"
    readonly property color accent: ({
        listening: "#d9b8ff", thinking: "#b77cff", searching: "#d3a4ff",
        weather: "#c9a0ff", preparing: "#c79aff", speaking: "#edc9ff",
        approval: "#ffd28a", controlling: "#f0c8ff", error: "#ff9fba", idle: "#c1a0ff"
    })[mode] || "#c1a0ff"

    Shape {
        id: halo
        x: 13; y: -2; width: 110; height: 112
        ShapePath {
            strokeColor: "transparent"; strokeWidth: 0
            fillGradient: RadialGradient {
                centerX: 55; centerY: 56; centerRadius: 56; focalX: 55; focalY: 56; focalRadius: 0
                GradientStop { position: 0.00; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.23) }
                GradientStop { position: 0.80; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.16) }
                GradientStop { position: 1.00; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0) }
            }
            PathAngleArc { centerX: 55; centerY: 56; radiusX: 55; radiusY: 56; startAngle: 0; sweepAngle: 360 }
        }
        SequentialAnimation on scale {
            running: root.motionEnabled
            loops: Animation.Infinite
            ScaleAnimator { from: 0.94; to: 1.04; duration: 3000; easing.type: Easing.InOutSine }
            ScaleAnimator { from: 1.04; to: 0.94; duration: 3000; easing.type: Easing.InOutSine }
        }
    }

    Item {
        id: sphere
        x: 16; y: 2; width: 104; height: 104
        transformOrigin: Item.Center

        // A slow, independent breath keeps the orb alive while the inner light
        // drifts. The small range avoids making the desktop widget feel busy.
        SequentialAnimation on scale {
            running: root.motionEnabled
            loops: Animation.Infinite
            ScaleAnimator { from: 0.985; to: 1.025; duration: 3600; easing.type: Easing.InOutSine }
            ScaleAnimator { from: 1.025; to: 0.985; duration: 4200; easing.type: Easing.InOutSine }
        }

        Shape {
            anchors.fill: parent
            ShapePath {
                strokeColor: "transparent"
                strokeWidth: 0
                fillGradient: LinearGradient {
                    x1: 14; y1: 0; x2: 88; y2: 104
                    GradientStop { position: 0.00; color: "#fffdfd" }
                    GradientStop { position: 0.18; color: "#e8f9ff" }
                    GradientStop { position: 0.38; color: "#bcecff" }
                    GradientStop { position: 0.58; color: "#62c4ff" }
                    GradientStop { position: 0.72; color: "#168bff" }
                    GradientStop { position: 0.86; color: "#405ce9" }
                    GradientStop { position: 1.00; color: "#762bd8" }
                }
                PathAngleArc { centerX: 52; centerY: 52; radiusX: 52; radiusY: 52; startAngle: 0; sweepAngle: 360 }
            }
        }

        Item {
            id: bloomClip
            anchors.fill: parent
            clip: true
            Shape {
                id: pearlBloom
                x: 8; y: 8; width: 88; height: 88
                ShapePath {
                    strokeColor: "transparent"; strokeWidth: 0
                    fillGradient: RadialGradient {
                        centerX: 44; centerY: 44; centerRadius: 44
                        focalX: 35; focalY: 32; focalRadius: 0
                        GradientStop { position: 0.00; color: "#c5ffffff" }
                        GradientStop { position: 0.42; color: "#75f6ebff" }
                        GradientStop { position: 0.78; color: "#30f3e6ff" }
                        GradientStop { position: 1.00; color: "#00f3e6ff" }
                    }
                    PathAngleArc { centerX: 44; centerY: 44; radiusX: 44; radiusY: 44; startAngle: 0; sweepAngle: 360 }
                }
                SequentialAnimation {
                    running: root.motionEnabled
                    loops: Animation.Infinite
                    ParallelAnimation {
                        XAnimator { target: pearlBloom; from: 4; to: 12; duration: 4600; easing.type: Easing.InOutSine }
                        YAnimator { target: pearlBloom; from: 4; to: 12; duration: 5700; easing.type: Easing.InOutSine }
                    }
                    ParallelAnimation {
                        XAnimator { target: pearlBloom; from: 12; to: 4; duration: 4600; easing.type: Easing.InOutSine }
                        YAnimator { target: pearlBloom; from: 12; to: 4; duration: 5700; easing.type: Easing.InOutSine }
                    }
                }
            }
            Shape {
                id: violetBloom
                x: 8; y: 8; width: 88; height: 88
                ShapePath {
                    strokeColor: "transparent"; strokeWidth: 0
                    fillGradient: RadialGradient {
                        centerX: 44; centerY: 44; centerRadius: 44
                        focalX: 55; focalY: 56; focalRadius: 0
                        GradientStop { position: 0.00; color: "#815f14bd" }
                        GradientStop { position: 0.48; color: "#604808b7" }
                        GradientStop { position: 0.82; color: "#259425ed" }
                        GradientStop { position: 1.00; color: "#009425ed" }
                    }
                    PathAngleArc { centerX: 44; centerY: 44; radiusX: 44; radiusY: 44; startAngle: 0; sweepAngle: 360 }
                }
                SequentialAnimation {
                    running: root.motionEnabled
                    loops: Animation.Infinite
                    ParallelAnimation {
                        XAnimator { target: violetBloom; from: 14; to: 22; duration: 6200; easing.type: Easing.InOutSine }
                        YAnimator { target: violetBloom; from: 12; to: 20; duration: 5100; easing.type: Easing.InOutSine }
                    }
                    ParallelAnimation {
                        XAnimator { target: violetBloom; from: 22; to: 14; duration: 6200; easing.type: Easing.InOutSine }
                        YAnimator { target: violetBloom; from: 20; to: 12; duration: 5100; easing.type: Easing.InOutSine }
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: 1
            border.color: "#55ffffff"
        }

        Item {
            id: voiceBars
            anchors.centerIn: parent
            width: 48; height: 30
            visible: root.mode === "listening" || root.mode === "speaking"
            Repeater {
                model: 5
                delegate: Rectangle {
                    id: bar
                    x: index * 10 + 2; y: 15 - height / 2
                    width: 3.2; height: 8 + ((index * 7) % 10); radius: 2
                    color: "#fffaff"; opacity: 0.92
                    SequentialAnimation on scale {
                        running: root.motionEnabled && voiceBars.visible
                        loops: Animation.Infinite
                        ScaleAnimator { from: 0.66; to: 1.24; duration: 240 + index * 37; easing.type: Easing.InOutSine }
                        ScaleAnimator { from: 1.24; to: 0.66; duration: 250 + index * 31; easing.type: Easing.InOutSine }
                    }
                }
            }
        }

        Item {
            id: thoughtGlint
            width: 13; height: 13
            visible: root.mode === "thinking" || root.mode === "preparing" || root.mode === "searching" || root.mode === "weather"
            Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: "#f7ecff"; opacity: 0.30 }
            Rectangle { anchors.centerIn: parent; width: 6; height: 6; radius: 3; color: "#ffffff" }
            SequentialAnimation {
                running: root.motionEnabled && thoughtGlint.visible
                loops: Animation.Infinite
                ParallelAnimation {
                    XAnimator { target: thoughtGlint; from: 45; to: 75; duration: 1050; easing.type: Easing.InOutSine }
                    YAnimator { target: thoughtGlint; from: 15; to: 45; duration: 1050; easing.type: Easing.InOutSine }
                }
                ParallelAnimation {
                    XAnimator { target: thoughtGlint; from: 75; to: 45; duration: 1050; easing.type: Easing.InOutSine }
                    YAnimator { target: thoughtGlint; from: 45; to: 75; duration: 1050; easing.type: Easing.InOutSine }
                }
                ParallelAnimation {
                    XAnimator { target: thoughtGlint; from: 45; to: 15; duration: 1050; easing.type: Easing.InOutSine }
                    YAnimator { target: thoughtGlint; from: 75; to: 45; duration: 1050; easing.type: Easing.InOutSine }
                }
                ParallelAnimation {
                    XAnimator { target: thoughtGlint; from: 15; to: 45; duration: 1050; easing.type: Easing.InOutSine }
                    YAnimator { target: thoughtGlint; from: 45; to: 15; duration: 1050; easing.type: Easing.InOutSine }
                }
            }
        }
    }

    Rectangle {
        id: statusBadge
        x: 15; y: 111; width: 106; height: 22; radius: 11
        color: "#ed211431"
        border.width: 1; border.color: "#70ead9ff"
        Rectangle { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: root.accent }
        Text {
            anchors.left: parent.left; anchors.leftMargin: 23
            anchors.right: parent.right; anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: root.statusText
            color: "#fffaff"
            font.family: "Sans Serif"; font.pixelSize: 9; font.weight: Font.DemiBold
            minimumPixelSize: 7; fontSizeMode: Text.Fit
        }
    }

    MouseArea {
        id: pointer
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
