PYTHON = venv/bin/python
SLICE2PY = venv/bin/slice2py

.PHONY: clean all ice client
all: ice logs client

$(PYTHON):
	python -m venv venv

$(SLICE2PY): $(PYTHON)
	venv/bin/python -m pip install zero-ice

ice: $(SLICE2PY)
	$(SLICE2PY) --underscore -Islices/ slices/types.ice slices/dashboard.ice slices/experiment.ice

logs:
	mkdir logs/

client:
	(cd mamba_client && make)

clean:
	rm -rf MambaICE/
	rm -rf logs/
	(cd mamba_client && make clean)
