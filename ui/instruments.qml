// R1 Instruments: the R1's battery and links, and this Mac's Gemini spend, as a panel of gauges on the reMarkable 2.
// From herd-board-serve's /r1.json, which reads the R1 over ssh at most every 30 s (numbers and states only). Read
// every 30 s here; the page redraws only when a reading changes. Tap anywhere to read now.
import QtQuick 2.5

Rectangle {
	id: root
	anchors.fill: parent
	color: "white"
	property string server: "@SERVER@"
	property var r1: ({})
	property var gem: ({ callers: {}, limited: 0, hold: 0 })
	property bool online: false
	property string seen: ""
	property string last: ""
	property var req: null
	readonly property string serif: "EB Garamond"
	readonly property string sans: "Noto Sans"

	property int tz: 0       // the Mac's offset from UTC: the tablet keeps UTC

	signal close
	function unloading() { tick.stop(); if (req) req.abort() }

	function hhmm(t) {
		var d = new Date((t + tz) * 1000)
		return ("0" + d.getUTCHours()).slice(-2) + ":" + ("0" + d.getUTCMinutes()).slice(-2)
	}
	function bars(dbm, lo, hi) { return dbm === null || dbm === undefined ? 0 : Math.max(0, Math.min(4, Math.round((dbm - lo) / (hi - lo) * 4))) }
	function uptime(s) {
		if (!s) return "—"
		var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600)
		return (d ? d + " d " : "") + h + " h"
	}
	function callers() {
		var out = []
		for (var k in gem.callers) out.push({ name: k, calls: gem.callers[k].calls, tokens: gem.callers[k].tokens })
		return out.sort(function(a, b) { return b.calls - a.calls })
	}
	function fetch() {
		if (req) req.abort()
		var x = new XMLHttpRequest()
		req = x
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE || x !== req) return
			req = null
			online = x.status === 200
			if (!online || x.responseText === last) return
			last = x.responseText
			var j = JSON.parse(x.responseText)
			tz = j.tz || 0
			r1 = j.r1
			gem = j.gemini
			seen = j.r1.seen ? hhmm(j.r1.seen) : ""
			dial.requestPaint()
		}
		x.open("GET", server + "/r1.json")
		x.send()
	}

	Component.onCompleted: fetch()
	Timer { id: tick; interval: 30000; repeat: true; running: true; onTriggered: fetch() }
	MouseArea { anchors.fill: parent; onClicked: fetch() }

	Column {
		id: page
		x: 72; y: 40; width: root.width - 144; spacing: 22

		Item {
			width: parent.width; height: 40
			Text { text: "INSTRUMENT PANEL"; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2 }
			Text { anchors.right: shut.left; anchors.rightMargin: 28; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2
				font.bold: !online || !r1.online
				text: !online ? "MAC UNREACHABLE" : r1.online ? "READ " + seen : "R1 OUT OF REACH" + (seen ? " SINCE " + seen : "") }
			Text { id: shut; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
				text: "×"; font.family: sans; font.pixelSize: 44
				MouseArea { anchors.fill: parent; anchors.margins: -30; onClicked: root.close() } }
		}
		Rectangle { width: parent.width; height: 2; color: "black" }
		Text { text: "R1 Instruments"; font.family: serif; font.pixelSize: 112; font.weight: Font.Black }
		Rectangle { width: parent.width; height: 6; color: "black" }

		// the battery dial, and its readings beside it
		Row {
			spacing: 48
			Item {
				width: 460; height: 460
				Canvas {
					id: dial
					anchors.fill: parent
					onPaint: {
						var c = getContext("2d"), cx = width / 2, cy = height / 2, r = width / 2 - 24
						var a0 = Math.PI * 0.75, span = Math.PI * 1.5, p = (r1.battery || 0) / 100
						c.reset()
						c.lineCap = "butt"
						c.strokeStyle = "#d0d0d0"; c.lineWidth = 34
						c.beginPath(); c.arc(cx, cy, r, a0, a0 + span); c.stroke()
						c.strokeStyle = "black"
						c.beginPath(); c.arc(cx, cy, r, a0, a0 + span * p); c.stroke()
						c.lineWidth = 3
						for (var i = 0; i <= 10; i++) {
							var a = a0 + span * i / 10
							c.beginPath(); c.moveTo(cx + Math.cos(a) * (r - 30), cy + Math.sin(a) * (r - 30))
							c.lineTo(cx + Math.cos(a) * (r - (i % 5 ? 44 : 58)), cy + Math.sin(a) * (r - (i % 5 ? 44 : 58))); c.stroke()
						}
					}
				}
				Column {
					anchors.centerIn: parent
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: r1.battery !== undefined && r1.battery !== null ? r1.battery + "%" : "—"
						font.family: serif; font.pixelSize: 120; font.weight: Font.Bold }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: r1.charging ? "CHARGING" : (r1.state || "").toUpperCase()
						font.family: sans; font.pixelSize: 24; font.letterSpacing: 3 }
				}
			}
			Column {
				spacing: 14; anchors.verticalCenter: parent.verticalCenter
				Text { text: "BATTERY"; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
				Text { text: (r1.mv ? (r1.mv / 1000).toFixed(2) + " V" : "—"); font.family: serif; font.pixelSize: 52 }
				Text { text: (r1.ma !== undefined && r1.ma !== null ? Math.abs(r1.ma) + " mA " + (r1.ma < 0 ? "drawn" : "in") : "—")
					font.family: serif; font.pixelSize: 52 }
				Item { width: 1; height: 12 }
				Text { text: "UP"; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
				Text { text: uptime(r1.uptime) + " · load " + (r1.load || "—"); font.family: serif; font.pixelSize: 40 }
			}
		}

		Rectangle { width: parent.width; height: 2; color: "black" }

		// the links: a gauge each
		Grid {
			columns: 2; columnSpacing: 40; rowSpacing: 30
			Repeater {
				model: [
					{ label: "LTE", on: r1.lte === "data" || r1.lte === "reg", value: !r1.lte || r1.lte === "off" ? "off" : r1.lte === "park" ? "parked" : r1.lte === "data" ? "data up" : "registered",
					  sub: r1.lte_dbm ? r1.lte_dbm + " dBm RSRP" : "no reading", n: bars(r1.lte_dbm, -125, -80) },
					{ label: "WI-FI", on: !!r1.wifi, value: r1.wifi ? "up" : "down", sub: r1.wifi_dbm ? r1.wifi_dbm + " dBm" : "no reading",
					  n: bars(r1.wifi_dbm, -90, -45) },
					{ label: "EARBUDS", on: !!r1.bt, value: r1.bt ? "connected" : "none", sub: "Bluetooth", n: r1.bt ? 4 : 0 },
					{ label: "TAILNET", on: !!r1.tailscale, value: r1.tailscale ? "joined" : "off", sub: "Tailscale", n: r1.tailscale ? 4 : 0 }
				]
				Rectangle {
					id: gauge
					property int n: modelData.n
					width: (page.width - 40) / 2; height: 170
					color: "white"; border.color: "black"; border.width: modelData.on ? 4 : 2
					Column {
						x: 28; y: 22; spacing: 6
						Text { text: modelData.label; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
						Text { text: modelData.value; font.family: serif; font.pixelSize: 52; font.weight: Font.Bold }
						Text { text: modelData.sub; font.family: sans; font.pixelSize: 22 }
					}
					Row {
						anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 28; spacing: 8
						Repeater {
							model: 4
							Rectangle { width: 18; height: 24 + index * 20; anchors.bottom: parent.bottom
								color: index < gauge.n ? "black" : "white"; border.color: "black"; border.width: 2 }
						}
					}
				}
			}
		}

		Rectangle { width: parent.width; height: 6; color: "black" }

		// this Mac's Gemini ledger
		Item {
			width: parent.width; height: 40
			Text { text: "GEMINI TODAY, ON THIS MAC"; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
			Text { anchors.right: parent.right; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2; font.bold: gem.hold > 0
				text: gem.hold > 0 ? "RESTING " + gem.hold + " S AFTER A 429" : gem.limited + " × 429 TODAY" }
		}
		Repeater {
			model: callers()
			Item {
				width: page.width; height: 52
				Text { text: modelData.name; font.family: serif; font.pixelSize: 36 }
				Text { anchors.right: parent.right; text: modelData.calls + " calls · " + Math.round(modelData.tokens / 100) / 10 + "k tokens"
					font.family: serif; font.pixelSize: 36 }
				Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "black" }
			}
		}
		Text { visible: callers().length === 0; text: "No calls yet today."; font.family: serif; font.italic: true; font.pixelSize: 32 }
	}
}
