#!/bin/sh -e

ext_sub() { echo "$2" | sed 's/\.[^.]*$'"/$1/"; }
for name in $(find . -name '*.ui'); do
	pyuic5 "$name" -o "$(ext_sub .py "$name")"; done
for name in $(find . -name '*.qrc'); do
	pyrcc5 "$name" -o "$(ext_sub .py "$name")"; done

