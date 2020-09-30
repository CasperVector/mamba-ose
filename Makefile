PYTHON = python
SLICE2PY = slice2py
RM = rm
RMDIR = rm -r

ifeq ($(OS), Windows_NT)
    PYTHON = venv/bin/python
    SLICE2PY = venv/bin/slice2py
    RM = rm
    RMDIR = rm -r
endif

.PHONY: clean all ice client server
all: ice logs client
server: ice

ice:
	$(SLICE2PY) --underscore -Islices/ slices/types.ice slices/dashboard.ice slices/experiment.ice

logs:
	mkdir logs/

client:
	(cd mamba_client && make)

clean:
	$(RMDIR) MambaICE/
	$(RMDIR) logs/
	(cd mamba_client && make clean)
