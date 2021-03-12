#!/bin/sh -e

ext_sub() { echo "$2" | sed 's/\.[^.]*$'"/$1/"; }
slice2py --underscore --output-dir . -I MambaICE/slices \
	MambaICE/slices/*.ice || true
for name in mamba_client/widgets/ui/*.ui; do
	pyuic5 "$name" -o "$(ext_sub .py "$name")"; done
for name in mamba_client/widgets/ui/*.qrc; do
	pyrcc5 "$name" -o "$(ext_sub .py "$name")"; done

