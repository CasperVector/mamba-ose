PYUIC5 = ../venv/bin/pyuic5
PYRCC5 = ../venv/bin/pyrcc5
TARGET_UI_FILES = widgets/ui/ui_scanmechanismwidget.py
TARGET_RES_FILES = widgets/ui/rc_icons.py

all: $(TARGET_UI_FILES) $(TARGET_RES_FILES)

$(PYUIC5) $(PYRRC5):
	../venv/bin/python -m pip install pyqt5

$(TARGET_UI_FILES): %.py: %.ui
	$(PYUIC5) $< -o $@

$(TARGET_RES_FILES): %.py: %.qrc
	$(PYRCC5) $< -o $@

clean:
	rm widgets/ui/*.py
