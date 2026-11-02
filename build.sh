#!/bin/bash
# build.sh URL: each app in apps/ (The Cyber Times, The Walk Edition, R1 Instruments, Field Dispatches, Correspondence) as an AppLoad
# app in output/ID/, fetching from herd-board-serve at URL (e.g. http://127.0.0.1:8791). rcc comes from Debian's Qt 6
# tools, in a docker image made once (herd-board-qt).
set -e
cd "$(dirname "$0")"
[ -n "$1" ] || { echo "usage: build.sh http://HOST:8791" >&2; exit 1; }
docker image inspect herd-board-qt >/dev/null 2>&1 || printf '%s\n' 'FROM debian:bookworm-slim' \
	'RUN apt-get -qq update && apt-get -qq install -y qt6-base-dev-tools >/dev/null' |
	docker build -q -t herd-board-qt - >/dev/null
rm -rf output build && mkdir -p output build
for m in apps/*/manifest.json; do
	id=$(basename "$(dirname "$m")"); qml=$(sed -n 's/.*"entry": *"\/\(.*\)".*/\1/p' "$m")
	mkdir -p "build/$id/ui"
	sed "s|@SERVER@|$1|" "$qml" >"build/$id/$qml"
	printf '<RCC>\n\t<qresource>\n\t\t<file>%s</file>\n\t</qresource>\n</RCC>\n' "$qml" >"build/$id/application.qrc"
done
docker run --rm -v "$PWD/build:/b" -w /b herd-board-qt sh -c \
	'set -e; for d in */; do (cd "$d" && /usr/lib/qt6/libexec/rcc --binary -no-compress -o resources.rcc application.qrc); done'
for d in build/*/; do id=$(basename "$d"); mkdir -p "output/$id"; cp "apps/$id/icon.png" "apps/$id/manifest.json" "$d/resources.rcc" "output/$id/"; done
rm -rf build
