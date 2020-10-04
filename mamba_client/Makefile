PYUIC5 = ../venv/bin/pyuic5
PYRCC5 = ../venv/bin/pyrcc5
TARGET_UI_FILES = widgets/ui/ui_scanmechanismwidget.py widgets/ui/ui_motorwidget.py
TARGET_RES_FILES = widgets/ui/rc_icons.py

ifeq ($(OS), Windows_NT)
    PYUIC5 = pyuic5
    PYRCC5 = pyrcc5
endif

all: $(TARGET_UI_FILES) $(TARGET_RES_FILES)

$(TARGET_UI_FILES): %.py: %.ui
	$(PYUIC5) $< -o $@

$(TARGET_RES_FILES): %.py: %.qrc
	$(PYRCC5) $< -o $@

clean:
	rm widgets/ui/*.py
